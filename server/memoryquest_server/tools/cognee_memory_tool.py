import os
import asyncio
import logging
import cognee
from typing import Any, MutableSequence, Sequence
from cognee.infrastructure.databases.vector import use_vector_adapter
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from cognee.exceptions import CogneeApiError
from agent_framework import ChatMessage, Context, ContextProvider
from dotenv import load_dotenv

from tools.cognee_azure_search_adapter import CogneeAzureSearchAdapter

load_dotenv()
logger = logging.getLogger(__name__)

# Timeout for Cognee operations to prevent hanging when the LLM deployment
# or vector DB is slow/unavailable.
COGNEE_TIMEOUT_SECONDS = float(os.getenv("COGNEE_TIMEOUT_SECONDS", "15"))


def _extract_username(messages, **kwargs):
    """Extract username from kwargs or from the system message 'You are assisting user X'."""
    username = kwargs.get("username")
    if username:
        return username
    import re
    msgs = [messages] if isinstance(messages, ChatMessage) else (messages or [])
    for msg in msgs:
        role = getattr(msg.role, "value", None) or str(msg.role)
        if role == "system":
            match = re.search(r"assisting user (\S+)", msg.text)
            if match:
                return match.group(1)
    return "anonymous"


class CogneeMemoryTool(ContextProvider):
    def __init__(self) -> None:
        logger.info("Initializing Cognee Memory Tool")
        self.dataset_name = os.getenv("COGNEE_DATASET_NAME") or "main_dataset"
        self._background_tasks: set[asyncio.Task] = set()
        self._setup_done = False
        self._setup_lock = asyncio.Lock()
        self._configure_cognee()
        self._register_vector_adapter()

    async def ensure_setup(self) -> None:
        """Lazily initialize Cognee's database schema on first use."""
        if self._setup_done:
            return
        async with self._setup_lock:
            if self._setup_done:
                return
            try:
                from cognee.modules.engine.operations.setup import setup
                logger.info("Running Cognee database setup...")
                await setup()
                self._setup_done = True
                logger.info("Cognee database setup complete.")
            except Exception as e:
                logger.error(f"Cognee setup failed: {e}")

    # --- ContextProvider interface ---

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called before the agent processes messages - injects relevant memories."""
        await self.ensure_setup()
        username = _extract_username(messages, **kwargs)
        dataset_name = self._dataset_name_for_user(username)

        # Dynamic retrieval: Use the user's last message as the query.
        # Meta-questions ("what do you remember about me") are poor search queries;
        # fall back to a broad query that retrieves general user facts.
        query = "user preferences and history"
        if isinstance(messages, Sequence) and messages:
            for msg in reversed(messages):
                role = getattr(msg.role, "value", None) or str(msg.role)
                if role == "user":
                    if len(msg.text) > 5:
                        meta_phrases = [
                            "remember about me", "know about me", "recall about me",
                            "what do you remember", "what do you know", "list every fact",
                        ]
                        if not any(p in msg.text.lower() for p in meta_phrases):
                            query = msg.text
                    break
        elif isinstance(messages, ChatMessage):
            if (getattr(messages.role, "value", None) or str(messages.role)) == "user" and len(messages.text) > 5:
                meta_phrases = [
                    "remember about me", "know about me", "recall about me",
                    "what do you remember", "what do you know", "list every fact",
                ]
                if not any(p in messages.text.lower() for p in meta_phrases):
                    query = messages.text

        logger.info(f"Cognee invoking search for user '{username}' with query: '{query}'")

        try:
            if not await self._dataset_exists(dataset_name):
                return Context(messages=[])

            results = await asyncio.wait_for(
                cognee.search(query_text=query, datasets=dataset_name),
                timeout=COGNEE_TIMEOUT_SECONDS,
            )
            memories = self._format_search_results(results)

            if not memories:
                return Context(messages=[])

            memory_block = "\n".join(f"- {m}" for m in memories)
            return Context(
                messages=[ChatMessage(role="system", text=f"Relevant Cognee memories:\n{memory_block}")]
            )
        except asyncio.CancelledError:
            logger.warning("Cognee invoking() cancelled (server shutting down)")
            return Context(messages=[])
        except asyncio.TimeoutError:
            logger.warning(f"Cognee search timed out after {COGNEE_TIMEOUT_SECONDS}s for user '{username}'")
            return Context(messages=[])
        except (DatasetNotFoundError, CogneeApiError) as exc:
            logger.info(f"Cognee search skipped (no prior data): {exc}")
            return Context(messages=[])
        except Exception as e:
            logger.error(f"Cognee search failed: {e}")
            return Context(messages=[])

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after processing. Stores conversation in background to improve performance."""
        username = _extract_username(request_messages, **kwargs)

        # Extract only user messages to avoid storing assistant output as user facts
        content_lines: list[str] = []

        def _extract(source: ChatMessage | Sequence[ChatMessage]) -> None:
            if isinstance(source, ChatMessage):
                role = getattr(source.role, "value", None) or str(source.role)
                if role == "user":
                    content_lines.append(f"{role}: {source.text}")
            elif isinstance(source, Sequence):
                for msg in source:
                    role = getattr(msg.role, "value", None) or str(msg.role)
                    if role == "user":
                        content_lines.append(f"{role}: {msg.text}")

        _extract(request_messages)

        content = "\n".join(content_lines)
        if not content.strip():
            return

        # Fire-and-forget: offload the heavy cognify to a background task
        task = asyncio.create_task(self._background_save(username, content))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    # --- Public API ---

    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
        """Retrieve memories for a given username from cognee."""
        await self.ensure_setup()
        dataset_name = self._dataset_name_for_user(username)
        search_query = query or "user preferences overview"

        try:
            if not await self._dataset_exists(dataset_name):
                return []

            results = await cognee.search(query_text=search_query, datasets=dataset_name)
            memories = self._format_search_results(results)
            return memories[:limit] if limit > 0 else memories
        except asyncio.CancelledError:
            logger.warning("Cognee get_memories cancelled (server shutting down)")
            return []
        except (DatasetNotFoundError, CogneeApiError) as exc:
            logger.info(f"Cognee get_memories skipped (no prior data): {exc}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return []

    async def delete_user_memories(self, username: str) -> dict[str, Any]:
        """Delete all stored Cognee memories for the given user."""
        dataset_name = self._dataset_name_for_user(username)
        try:
            datasets_api = cognee.datasets()
            all_datasets = await datasets_api.list_datasets()
            target = next((ds for ds in all_datasets if getattr(ds, "name", None) == dataset_name), None)

            if not target:
                return {"deleted": False, "reason": "dataset_not_found"}

            await datasets_api.delete_dataset(str(target.id))
            return {"deleted": True, "dataset": dataset_name}
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return {"deleted": False, "reason": str(e)}

    # --- Private helpers ---

    async def _background_save(self, username: str, content: str) -> None:
        """Background task to add data and rebuild knowledge graph."""
        await self.ensure_setup()
        dataset_name = self._dataset_name_for_user(username)
        try:
            logger.debug(f"Background: Adding content for {dataset_name}")
            await asyncio.wait_for(
                cognee.add(content, dataset_name=dataset_name),
                timeout=COGNEE_TIMEOUT_SECONDS,
            )

            logger.debug(f"Background: Running cognify for {dataset_name}")
            # cognify can be very slow (builds knowledge graph); give it more time
            await asyncio.wait_for(
                cognee.cognify(datasets=dataset_name),
                timeout=COGNEE_TIMEOUT_SECONDS * 4,
            )
            logger.info(f"Background: Cognee memory updated for user {username}")
        except asyncio.TimeoutError:
            logger.warning(f"Background Cognee save timed out for {username}")
        except asyncio.CancelledError:
            logger.warning(f"Background save cancelled for {username}")
        except Exception as e:
            logger.error(f"Background Cognee update failed for {username}: {e}")

    async def shutdown(self) -> None:
        """Cancel pending background tasks and wait for them to finish."""
        if not self._background_tasks:
            return
        logger.info(f"Shutting down: waiting for {len(self._background_tasks)} Cognee background task(s)...")
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        logger.info("Cognee background tasks cleaned up.")

    def _dataset_name_for_user(self, username: str) -> str:
        safe = (username or "anonymous").strip() or "anonymous"
        return f"{self.dataset_name}__{safe}"

    def _format_search_results(self, results: Any) -> list[str]:
        """Extract clean text strings from Cognee search results."""
        texts: list[str] = []
        if not results:
            return texts

        for result in results:
            val = result.get("search_result") if isinstance(result, dict) else getattr(result, "search_result", None)
            if val:
                if isinstance(val, list):
                    texts.extend(str(v) for v in val)
                else:
                    texts.append(str(val))
        return texts

    async def _dataset_exists(self, dataset_name: str) -> bool:
        try:
            datasets = await cognee.datasets().list_datasets()
            return any(getattr(ds, "name", None) == dataset_name for ds in datasets)
        except Exception:
            return True

    def _configure_cognee(self) -> None:
        """Map generic environment variables to Cognee specific variables."""
        # LLM Configuration
        llm_endpoint = os.getenv("LLM_ENDPOINT", "")
        llm_api_key = os.getenv("LLM_API_KEY", "")
        llm_api_version = os.getenv("LLM_API_VERSION", "")
        llm_model = os.getenv("LLM_MODEL", "")

        # Embedding Configuration
        embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT", "")
        embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
        embedding_model = os.getenv("EMBEDDING_MODEL", "")

        # Vector DB Configuration — use Azure AI Search instead of Qdrant
        azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
        azure_search_api_key = os.getenv("AZURE_SEARCH_API_KEY", "")
        vector_db_provider = "azureaisearch"

        # Set cognee-specific environment variables
        os.environ["COGNEE_LLM_ENDPOINT"] = llm_endpoint
        os.environ["COGNEE_LLM_API_KEY"] = llm_api_key
        os.environ["COGNEE_LLM_API_VERSION"] = llm_api_version
        os.environ["COGNEE_LLM_MODEL"] = llm_model

        os.environ["COGNEE_VECTOR_DB_ENDPOINT"] = embedding_endpoint
        os.environ["COGNEE_VECTOR_DB_API_KEY"] = embedding_api_key
        os.environ["COGNEE_VECTOR_DB_EMBEDDING_MODEL"] = embedding_model
        os.environ["COGNEE_VECTOR_DB_PROVIDER"] = vector_db_provider
        os.environ["COGNEE_VECTOR_DB_URL"] = azure_search_endpoint
        os.environ["COGNEE_VECTOR_DB_KEY"] = azure_search_api_key

        # Relational (SQLite) storage — ensure Cognee writes to a writable path
        db_path = os.getenv("DB_PATH", "/tmp/cognee_data/databases")
        db_name = os.getenv("DB_NAME", "cognee_db")
        os.environ["DB_PATH"] = db_path
        os.environ["DB_NAME"] = db_name
        os.makedirs(db_path, exist_ok=True)

        print(
            f"Cognee configured: LLM={llm_model}, Embedding={embedding_model}, "
            f"VectorDB={vector_db_provider} at {azure_search_endpoint}, "
            f"RelationalDB=sqlite at {db_path}/{db_name}, dataset={self.dataset_name}"
        )

    def _register_vector_adapter(self) -> None:
        try:
            use_vector_adapter("azureaisearch", CogneeAzureSearchAdapter)
            logger.info("Registered CogneeAzureSearchAdapter for Cognee")
        except Exception as exc:
            print(f"Cognee Azure Search adapter register failed: {exc}")
