import os
import asyncio
import logging
import cognee
from typing import Any, MutableSequence, Sequence
from cognee_community_vector_adapter_qdrant import register
from cognee_community_vector_adapter_qdrant.qdrant_adapter import QDrantAdapter
from qdrant_client import AsyncQdrantClient
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from agent_framework import ChatMessage, Context, ContextProvider
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


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
            # Strip any port that may have been appended to the URL
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
        self._configure_cognee()
        self._register_vector_adapter()

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called before the agent processes messages - injects relevant memories."""
        username = kwargs.get("username") or "anonymous"
        dataset_name = self._dataset_name_for_user(username)

        # Dynamic retrieval: Use the user's last message as the query
        query = "user preferences and history"
        if isinstance(messages, Sequence) and messages:
            for msg in reversed(messages):
                role = getattr(msg.role, "value", None) or str(msg.role)
                if role == "user":
                    query = msg.text
                    break
        elif isinstance(messages, ChatMessage):
             if (getattr(messages.role, "value", None) or str(messages.role)) == "user":
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
        except (DatasetNotFoundError, Exception) as e:
            logger.error(f"Cognee search failed: {e}")
            return Context(messages=[])

    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any) -> None:
        """Called after processing. Stores conversation in background to improve performance."""
        username = kwargs.get("username") or "anonymous"

        # Extract text content
        content_lines = []
        def _extract(source):
            if isinstance(source, ChatMessage):
                role = getattr(source.role, "value", None) or str(source.role)
                content_lines.append(f"{role}: {source.text}")
            elif isinstance(source, Sequence):
                for msg in source:
                    role = getattr(msg.role, "value", None) or str(msg.role)
                    content_lines.append(f"{role}: {msg.text}")

        _extract(request_messages)
        if response_messages:
            _extract(response_messages)
        
        content = "\n".join(content_lines)

        # Performance: Offload the heavy 'cognify' process to a background task
        # so we don't block the HTTP response to the user.
        task = asyncio.create_task(self._background_save(username, content))
        task.add_done_callback(lambda t: None) # clear reference logic if needed, usually fine in fire-and-forget

    async def _background_save(self, username: str, content: str):
        """Background task to add data and rebuild knowledge graph."""
        dataset_name = self._dataset_name_for_user(username)
        try:
            logger.debug(f"Background: Adding content for {dataset_name}")
            await cognee.add(content, dataset_name=dataset_name)
            
            # This is the expensive operation
            logger.debug(f"Background: Running cognify for {dataset_name}")
            await cognee.cognify(datasets=dataset_name)
            logger.info(f"Background: Cognee memory updated for user {username}")
        except Exception as e:
            logger.error(f"Background Cognee update failed for {username}: {e}")

    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
        """Retrieve memories for a given username from cognee."""
        dataset_name = self._dataset_name_for_user(username)
        search_query = query or "user preferences overview"

        try:
            if not await self._dataset_exists(dataset_name):
                return []

            results = await cognee.search(query_text=search_query, datasets=dataset_name)
            memories = self._format_search_results(results)
            return memories[:limit] if limit > 0 else memories
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

    # --- Helper Methods ---

    def _dataset_name_for_user(self, username: str) -> str:
        safe = (username or "anonymous").strip() or "anonymous"
        return f"{self.dataset_name}__{safe}"

    def _format_search_results(self, results: Any) -> list[str]:
        """Extract clean text strings from Cognee search results."""
        texts: list[str] = []
        if not results:
            return texts

        for result in results:
            # Handle results that might be objects or dicts
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
        config_map = {
            "COGNEE_LLM_ENDPOINT": "LLM_ENDPOINT",
            "COGNEE_LLM_API_KEY": "LLM_API_KEY",
            "COGNEE_LLM_API_VERSION": "LLM_API_VERSION",
            "COGNEE_LLM_MODEL": "LLM_MODEL",
            "COGNEE_VECTOR_DB_ENDPOINT": "EMBEDDING_ENDPOINT",
            "COGNEE_VECTOR_DB_API_KEY": "EMBEDDING_API_KEY",
            "COGNEE_VECTOR_DB_EMBEDDING_MODEL": "EMBEDDING_MODEL",
            "COGNEE_VECTOR_DB_URL": "VECTOR_DB_URL",
        }

        for cognee_key, env_key in config_map.items():
            if val := os.getenv(env_key):
                os.environ[cognee_key] = val
        
        # Explicit defaults/logic
        os.environ["COGNEE_VECTOR_DB_PROVIDER"] = os.getenv("VECTOR_DB_PROVIDER", "qdrant")

    def _register_vector_adapter(self) -> None:
        try:
            register.use_vector_adapter("qdrant", CustomQDrantAdapter)
            logger.info("Registered CustomQDrantAdapter for Cognee")
        except Exception as exc:
            logger.warning(f"Cognee Qdrant adapter register failed: {exc}")