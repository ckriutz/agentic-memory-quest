"""Cognee ContextProvider backed by Azure Cosmos DB for NoSQL.

This is the Cosmos Edition variant of ``cognee_memory_tool.py``.  The only
difference is the vector adapter registration which uses
``CogneeCosmosAdapter`` instead of ``CogneeAzureSearchAdapter``.
"""

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

from tools.cognee_cosmos_adapter import CogneeCosmosAdapter

load_dotenv()
logger = logging.getLogger(__name__)

COGNEE_TIMEOUT_SECONDS = float(os.getenv("COGNEE_TIMEOUT_SECONDS", "15"))


def _extract_username(messages, **kwargs):
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


class CogneeCosmosMemoryTool(ContextProvider):
    def __init__(self) -> None:
        logger.info("Initializing Cognee Cosmos Memory Tool")
        self.dataset_name = os.getenv("COGNEE_DATASET_NAME") or "main_dataset"
        self._background_tasks: set[asyncio.Task] = set()
        self._setup_done = False
        self._setup_lock = asyncio.Lock()
        self._configure_cognee()
        self._register_vector_adapter()

    async def ensure_setup(self) -> None:
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

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        await self.ensure_setup()
        username = _extract_username(messages, **kwargs)
        dataset_name = self._dataset_name_for_user(username)

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

        logger.info(f"Cognee Cosmos invoking search for user '{username}' with query: '{query}'")

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
            return Context(messages=[])
        except asyncio.TimeoutError:
            logger.warning(f"Cognee Cosmos search timed out after {COGNEE_TIMEOUT_SECONDS}s")
            return Context(messages=[])
        except (DatasetNotFoundError, CogneeApiError) as exc:
            logger.info(f"Cognee Cosmos search skipped (no prior data): {exc}")
            return Context(messages=[])
        except Exception as e:
            logger.error(f"Cognee Cosmos search failed: {e}")
            return Context(messages=[])

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        username = _extract_username(request_messages, **kwargs)

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

        task = asyncio.create_task(self._background_save(username, content))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
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
            return []
        except (DatasetNotFoundError, CogneeApiError) as exc:
            logger.info(f"Cognee Cosmos get_memories skipped: {exc}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return []

    async def delete_user_memories(self, username: str) -> dict[str, Any]:
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

    async def _background_save(self, username: str, content: str) -> None:
        await self.ensure_setup()
        dataset_name = self._dataset_name_for_user(username)
        try:
            await asyncio.wait_for(
                cognee.add(content, dataset_name=dataset_name),
                timeout=COGNEE_TIMEOUT_SECONDS,
            )
            await asyncio.wait_for(
                cognee.cognify(datasets=dataset_name),
                timeout=COGNEE_TIMEOUT_SECONDS * 4,
            )
            logger.info(f"Cognee Cosmos memory updated for user {username}")
        except asyncio.TimeoutError:
            logger.warning(f"Background Cognee Cosmos save timed out for {username}")
        except asyncio.CancelledError:
            logger.warning(f"Background Cognee Cosmos save cancelled for {username}")
        except Exception as e:
            logger.error(f"Background Cognee Cosmos update failed for {username}: {e}")

    async def shutdown(self) -> None:
        if not self._background_tasks:
            return
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

    def _dataset_name_for_user(self, username: str) -> str:
        safe = (username or "anonymous").strip() or "anonymous"
        return f"{self.dataset_name}__{safe}"

    def _format_search_results(self, results: Any) -> list[str]:
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
        """Map environment variables for Cognee — Cosmos DB edition."""
        llm_endpoint = os.getenv("LLM_ENDPOINT", "")
        llm_api_key = os.getenv("LLM_API_KEY", "")
        llm_api_version = os.getenv("LLM_API_VERSION", "")
        llm_model = os.getenv("LLM_MODEL", "")

        embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT", "")
        embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
        embedding_model = os.getenv("EMBEDDING_MODEL", "")

        # Vector DB — Cosmos DB endpoint
        cosmos_endpoint = os.getenv("COSMOS_ENDPOINT", "")
        cosmos_key = os.getenv("COSMOS_KEY", "")
        vector_db_provider = "cosmos"

        os.environ["COGNEE_LLM_ENDPOINT"] = llm_endpoint
        os.environ["COGNEE_LLM_API_KEY"] = llm_api_key
        os.environ["COGNEE_LLM_API_VERSION"] = llm_api_version
        os.environ["COGNEE_LLM_MODEL"] = llm_model

        os.environ["COGNEE_VECTOR_DB_ENDPOINT"] = embedding_endpoint
        os.environ["COGNEE_VECTOR_DB_API_KEY"] = embedding_api_key
        os.environ["COGNEE_VECTOR_DB_EMBEDDING_MODEL"] = embedding_model
        os.environ["COGNEE_VECTOR_DB_PROVIDER"] = vector_db_provider
        os.environ["COGNEE_VECTOR_DB_URL"] = cosmos_endpoint
        os.environ["COGNEE_VECTOR_DB_KEY"] = cosmos_key

        db_path = os.getenv("DB_PATH", "/tmp/cognee_data/databases")
        db_name = os.getenv("DB_NAME", "cognee_db")
        os.environ["DB_PATH"] = db_path
        os.environ["DB_NAME"] = db_name
        os.makedirs(db_path, exist_ok=True)

        print(
            f"Cognee Cosmos configured: LLM={llm_model}, Embedding={embedding_model}, "
            f"VectorDB=cosmos at {cosmos_endpoint}, "
            f"RelationalDB=sqlite at {db_path}/{db_name}, dataset={self.dataset_name}"
        )

    def _register_vector_adapter(self) -> None:
        try:
            use_vector_adapter("cosmos", CogneeCosmosAdapter)
            logger.info("Registered CogneeCosmosAdapter for Cognee")
        except Exception as exc:
            print(f"Cognee Cosmos adapter register failed: {exc}")
