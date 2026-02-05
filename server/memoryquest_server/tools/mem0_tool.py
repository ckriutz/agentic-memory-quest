import os
import asyncio
import logging
from dotenv import load_dotenv
from agent_framework import ContextProvider, Context, ChatMessage
from mem0 import AsyncMemory
from collections.abc import MutableSequence, Sequence
from typing import Any
from qdrant_client import QdrantClient

load_dotenv()
logger = logging.getLogger(__name__)

class Mem0Tool(ContextProvider):
    def __init__(self) -> None:
        print("Initializing Mem0 Tool")
        self._memory: AsyncMemory | None = None
        self._memory_lock = asyncio.Lock()
        
        # Initialize configuration immediately OR lazily.
        # Encapsulating it ensures we pick up env vars at instantiation.
        self._qdrant_client = QdrantClient(url=os.getenv("QDRANT_HOST"), port=443)
        
        self._config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "client": self._qdrant_client,
                    "collection_name": "mem0"
                },
            },
            "llm": {
                "provider": "azure_openai",
                "config": {
                    "model": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                    "azure_kwargs": {
                        "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                        "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
                        "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
                        "api_key": os.environ["AZURE_OPENAI_API_KEY"],
                    }
                }
            },
            "embedder": {
                "provider": "azure_openai",
                "config": {
                    "model": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
                    "azure_kwargs": {
                        "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
                        "azure_deployment": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
                        "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
                        "api_key": os.environ["AZURE_OPENAI_API_KEY"],
                    }
                }
            }
        }

    async def _ensure_memory(self) -> AsyncMemory:
        if self._memory is not None:
            return self._memory
        async with self._memory_lock:
            if self._memory is None:
                self._memory = await AsyncMemory.from_config(self._config)
        return self._memory

    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
        if not username:
            return []
        memory = await self._ensure_memory()
        search_query = query or "user preferences and history"
        try:
            results = await memory.search(user_id=username, query=search_query, limit=limit)
            memories = results.get("results", []) if isinstance(results, dict) else []
            lines: list[str] = []
            for item in memories:
                if isinstance(item, dict):
                    memory_text = item.get("memory") or item.get("text") or item.get("content")
                    if memory_text:
                        lines.append(memory_text)
            return lines
        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return []

    async def delete_user_memories(self, username: str) -> dict[str, Any]:
        """Delete all memories for a specific user to match Hindsight/Cognee patterns."""
        if not username:
            return {"deleted": False, "reason": "no_username"}
        
        try:
            memory = await self._ensure_memory()
            if hasattr(memory, "delete_all"):
                result = await memory.delete_all(user_id=username)
                return {"deleted": True, "user_id": username, "result": result}

            # Older mem0 versions may only support reset(), which clears all users.
            # We intentionally do not call reset() here.
            return {
                "deleted": False,
                "reason": "mem0_missing_delete_all",
                "detail": "AsyncMemory.delete_all(user_id=...) is not available; upgrade mem0.",
            }
        except Exception as e:
            logger.error(f"Error deleting memories for {username}: {e}")
            return {"deleted": False, "reason": str(e)}

    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any,) -> None:
        """Stores memory. Using create_task to be non-blocking (Fire-and-Forget)."""
        username = kwargs.get("username")
        if not username:
            return

        def _normalize_role(role: Any) -> str:
            return getattr(role, "value", None) or str(role)

        def _append_messages(source: ChatMessage | Sequence[ChatMessage]) -> list[dict[str, str]]:
            if isinstance(source, ChatMessage):
                return [{"role": _normalize_role(source.role), "content": source.text}]
            return [{"role": _normalize_role(msg.role), "content": msg.text} for msg in source]

        messages: list[dict[str, str]] = []
        messages.extend(_append_messages(request_messages))
        if response_messages is not None:
            messages.extend(_append_messages(response_messages))

        # Performance Improvement: Offload the storage to a background task
        # so we don't block the response to the user.
        asyncio.create_task(self._background_add(username, messages))

    async def _background_add(self, username: str, messages: list[dict[str, str]]):
        try:
            memory = await self._ensure_memory()
            print(f"Mem0Agent storing memories for: {username} (background)")
            await memory.add(user_id=username, messages=messages)
        except Exception as exc:
            logger.error(f"Mem0 background add failed: {exc}")

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        username = kwargs.get("username")
        if not username:
            return Context(messages=[])

        memory = await self._ensure_memory()

        # Consistency: Match Hindsight's logic for extracting the query
        search_query = "user preferences and history"
        
        if isinstance(messages, MutableSequence) and messages:
            for msg in reversed(messages):
                role = getattr(msg.role, "value", None) or str(msg.role)
                if role == "user":
                    # Fallback logic: If the user just says "Yes" or "Okay", searching that is useless.
                    if len(msg.text) > 5:
                        search_query = msg.text
                    break
        
        print(f"Mem0Agent search query: {search_query}")
        
        try:
            results = await memory.search(user_id=username, query=search_query, limit=5)
            memories = results.get("results", []) if isinstance(results, dict) else []
            
            lines: list[str] = []
            for item in memories:
                if isinstance(item, dict):
                    memory_text = item.get("memory") or item.get("text") or item.get("content")
                    if memory_text:
                        lines.append(f"- {memory_text}")
            
            if not lines:
                return Context(messages=[])
                
            context_text = "Stored memories relevant to current REQUEST:\n" + "\n".join(lines)
            return Context(messages=[ChatMessage(role="system", text=context_text)])
            
        except Exception as e:
            logger.error(f"Error during memory search invoking: {e}")
            return Context(messages=[])
