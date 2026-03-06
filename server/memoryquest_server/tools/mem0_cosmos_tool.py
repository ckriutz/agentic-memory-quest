"""Mem0 ContextProvider backed by Azure Cosmos DB for NoSQL.

This is the Cosmos Edition variant of ``mem0_tool.py``.  The only difference
is the ``vector_store`` config block which injects a custom Cosmos DB client
via the ``client`` key instead of using Azure AI Search or Qdrant.
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
from agent_framework import ContextProvider, Context, ChatMessage
from mem0 import AsyncMemory
from collections.abc import MutableSequence, Sequence
from typing import Any

from tools.mem0_cosmos_vector_store import Mem0CosmosVectorStore

load_dotenv()
logger = logging.getLogger(__name__)

MEM0_TIMEOUT_SECONDS = float(os.getenv("MEM0_TIMEOUT_SECONDS", "10"))


def _extract_username(messages, **kwargs):
    """Extract username from kwargs or from the system message 'You are assisting user X'."""
    import re
    username = kwargs.get("username")
    if username:
        return username
    msgs = [messages] if isinstance(messages, ChatMessage) else (messages or [])
    for msg in msgs:
        role = getattr(msg.role, "value", None) or str(msg.role)
        if role == "system":
            match = re.search(r"assisting user (\S+)", msg.text)
            if match:
                return match.group(1)
    return None


class Mem0CosmosTool(ContextProvider):
    def __init__(self) -> None:
        print("Initializing Mem0 Cosmos Tool")
        self._memory: AsyncMemory | None = None
        self._memory_lock = asyncio.Lock()

        cosmos_endpoint = os.getenv("COSMOS_ENDPOINT", "")
        cosmos_key = os.getenv("COSMOS_KEY", "")

        # Build the custom Cosmos vector store client
        self._cosmos_store = Mem0CosmosVectorStore(
            cosmos_endpoint=cosmos_endpoint,
            cosmos_key=cosmos_key,
            collection_name="mem0-vectors",
            embedding_model_dims=1536,
        )

        self._config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "mem0-vectors",
                    "embedding_model_dims": 1536,
                    "client": self._cosmos_store,
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
        if not username:
            return {"deleted": False, "reason": "no_username"}
        try:
            memory = await self._ensure_memory()
            if hasattr(memory, "delete_all"):
                result = await memory.delete_all(user_id=username)
                return {"deleted": True, "user_id": username, "result": result}
            return {
                "deleted": False,
                "reason": "mem0_missing_delete_all",
                "detail": "AsyncMemory.delete_all(user_id=...) is not available.",
            }
        except Exception as e:
            logger.error(f"Error deleting memories for {username}: {e}")
            return {"deleted": False, "reason": str(e)}

    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any,) -> None:
        username = _extract_username(request_messages, **kwargs)
        if not username:
            return

        def _normalize_role(role: Any) -> str:
            return getattr(role, "value", None) or str(role)

        def _append_messages(source: ChatMessage | Sequence[ChatMessage]) -> list[dict[str, str]]:
            if isinstance(source, ChatMessage):
                role = _normalize_role(source.role)
                if role != "user":
                    return []
                return [{"role": role, "content": source.text}]
            out: list[dict[str, str]] = []
            for msg in source:
                role = _normalize_role(msg.role)
                if role == "user":
                    out.append({"role": role, "content": msg.text})
            return out

        messages: list[dict[str, str]] = []
        messages.extend(_append_messages(request_messages))

        if not messages:
            return

        asyncio.create_task(self._background_add(username, messages))

    async def _background_add(self, username: str, messages: list[dict[str, str]]):
        try:
            memory = await self._ensure_memory()
            print(f"Mem0 Cosmos storing memories for: {username} (background)")
            await asyncio.wait_for(
                memory.add(user_id=username, messages=messages),
                timeout=MEM0_TIMEOUT_SECONDS * 3,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Mem0 Cosmos background add timed out for user {username}")
        except Exception as exc:
            logger.error(f"Mem0 Cosmos background add failed: {exc}")

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        username = _extract_username(messages, **kwargs)
        if not username:
            return Context(messages=[])

        memory = await self._ensure_memory()
        search_query = "user preferences and history"

        if isinstance(messages, MutableSequence) and messages:
            for msg in reversed(messages):
                role = getattr(msg.role, "value", None) or str(msg.role)
                if role == "user":
                    if len(msg.text) > 5:
                        search_query = msg.text
                    break

        print(f"Mem0 Cosmos search query: {search_query}")

        try:
            results = await asyncio.wait_for(
                memory.search(user_id=username, query=search_query, limit=5),
                timeout=MEM0_TIMEOUT_SECONDS,
            )
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

        except asyncio.TimeoutError:
            logger.warning(f"Mem0 Cosmos search timed out after {MEM0_TIMEOUT_SECONDS}s for user {username}")
            return Context(messages=[])
        except Exception as e:
            logger.error(f"Error during memory search invoking: {e}")
            return Context(messages=[])
