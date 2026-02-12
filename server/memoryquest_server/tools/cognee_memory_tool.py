import os
import asyncio
import logging
import cognee
from typing import Any, MutableSequence, Sequence
from cognee_community_vector_adapter_qdrant import register
from cognee_community_vector_adapter_qdrant.qdrant_adapter import QDrantAdapter
from qdrant_client import AsyncQdrantClient
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from cognee.exceptions import CogneeApiError
from agent_framework import ChatMessage, Context, ContextProvider
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


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


class CustomQDrantAdapter(QDrantAdapter):
    """Custom QDrant adapter that properly handles HTTPS URLs.
    
    The default QDrantAdapter passes port=6333 even for HTTPS URLs, which causes
    connection issues. For HTTPS URLs, we must explicitly set port=443.
    """
    
    def get_qdrant_client(self) -> AsyncQdrantClient:
        if hasattr(self, 'qdrant_path') and self.qdrant_path is not None:
            return AsyncQdrantClient(path=self.qdrant_path)
        elif self.url is not None:
            url = self.url
            if url.startswith("https://"):
                import re
                url = re.sub(r':\d+/?$', '', url)
                url = url.rstrip('/')
                return AsyncQdrantClient(url=url, api_key=self.api_key, port=443)
            else:
                return AsyncQdrantClient(url=url, api_key=self.api_key, port=6333)
        return AsyncQdrantClient(location=":memory:")


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

        # Dynamic retrieval: Use the user's last message as the query
        query = "user preferences and history"
        if isinstance(messages, Sequence) and messages:
            for msg in reversed(messages):
                role = getattr(msg.role, "value", None) or str(msg.role)
                if role == "user":
                    # Short messages like "Yes" or "Ok" produce poor vector search results;
                    # fall back to the generic query in that case.
                    if len(msg.text) > 5:
                        query = msg.text
                    break
        elif isinstance(messages, ChatMessage):
            if (getattr(messages.role, "value", None) or str(messages.role)) == "user" and len(messages.text) > 5:
                query = messages.text

        logger.info(f"Cognee invoking search for user '{username}' with query: '{query}'")

        try:
            if not await self._dataset_exists(dataset_name):
                return Context(messages=[])

            results = await cognee.search(query_text=query, datasets=dataset_name)
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
            await cognee.add(content, dataset_name=dataset_name)

            logger.debug(f"Background: Running cognify for {dataset_name}")
            await cognee.cognify(datasets=dataset_name)
            logger.info(f"Background: Cognee memory updated for user {username}")
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

        # Vector DB Configuration
        vector_db_url = os.getenv("VECTOR_DB_URL", "")
        vector_db_provider = os.getenv("VECTOR_DB_PROVIDER", "qdrant")

        # Set cognee-specific environment variables
        os.environ["COGNEE_LLM_ENDPOINT"] = llm_endpoint
        os.environ["COGNEE_LLM_API_KEY"] = llm_api_key
        os.environ["COGNEE_LLM_API_VERSION"] = llm_api_version
        os.environ["COGNEE_LLM_MODEL"] = llm_model

        os.environ["COGNEE_VECTOR_DB_ENDPOINT"] = embedding_endpoint
        os.environ["COGNEE_VECTOR_DB_API_KEY"] = embedding_api_key
        os.environ["COGNEE_VECTOR_DB_EMBEDDING_MODEL"] = embedding_model
        os.environ["COGNEE_VECTOR_DB_PROVIDER"] = vector_db_provider
        os.environ["COGNEE_VECTOR_DB_URL"] = vector_db_url

        # Relational (SQLite) storage — ensure Cognee writes to a writable path
        db_path = os.getenv("DB_PATH", "/tmp/cognee_data/databases")
        db_name = os.getenv("DB_NAME", "cognee_db")
        os.environ["DB_PATH"] = db_path
        os.environ["DB_NAME"] = db_name
        os.makedirs(db_path, exist_ok=True)

        print(
            f"Cognee configured: LLM={llm_model}, Embedding={embedding_model}, "
            f"VectorDB={vector_db_provider} at {vector_db_url}, "
            f"RelationalDB=sqlite at {db_path}/{db_name}, dataset={self.dataset_name}"
        )

    def _register_vector_adapter(self) -> None:
        try:
            register.use_vector_adapter("qdrant", CustomQDrantAdapter)
            logger.info("Registered CustomQDrantAdapter for Cognee")
        except Exception as exc:
            print(f"Cognee Qdrant adapter register failed: {exc}")
