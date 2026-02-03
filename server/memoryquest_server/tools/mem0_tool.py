import os
import asyncio
from dotenv import load_dotenv
from agent_framework import ContextProvider, Context, ChatMessage
from agent_framework.mem0 import Mem0Provider
from mem0 import AsyncMemory, Memory
from collections.abc import MutableSequence, Sequence
from typing import Any
from qdrant_client import QdrantClient

load_dotenv()

# Pre-initialize Qdrant client to ensure correct port usage
# mem0's Qdrant wrapper ignores 'port' if 'host' is not provided, so we must inject the client directly
qdrant_client = QdrantClient(url=os.getenv("QDRANT_HOST"), port=443)

config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "client": qdrant_client,
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


class Mem0Tool(ContextProvider):
    def __init__(self) -> None:
        print("Initializing Mem0 Tool")
        self._memory: AsyncMemory | None = None
        self._memory_lock = asyncio.Lock()

    async def _ensure_memory(self) -> AsyncMemory:
        if self._memory is not None:
            return self._memory
        async with self._memory_lock:
            if self._memory is None:
                self._memory = await AsyncMemory.from_config(config)
        return self._memory

    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
        if not username:
            return []
        memory = await self._ensure_memory()
        search_query = query or "user preferences and history"
        results = await memory.search(user_id=username, query=search_query, limit=limit)
        memories = results.get("results", []) if isinstance(results, dict) else []
        lines: list[str] = []
        for item in memories:
            if isinstance(item, dict):
                memory_text = item.get("memory") or item.get("text") or item.get("content")
                if memory_text:
                    lines.append(memory_text)
        return lines

    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any,) -> None:
        print("Mem0Agent invoked")
        memory = await self._ensure_memory()
        username = kwargs.get("username")
        if not username:
            print("No username provided, skipping memory save")
            return
        print(f"Mem0Agent username: {username}")

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

        print(messages)
        try:
            result = await memory.add(user_id=username, messages=messages)
            print(f"Mem0 add result: {result}")
        except Exception as exc:
            print(f"Mem0 add failed: {exc}")

    # Improved to use contextual search based on latest user message.
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        username = kwargs.get("username")
        print(f"Mem0Agent invoking username: {username}")
        if not username:
            return Context(messages=[])

        memory = await self._ensure_memory()

        # Extract the user's latest message for contextual search
        latest_query = ""
        if isinstance(messages, MutableSequence) and messages:
            for msg in reversed(messages):
                role = getattr(msg.role, "value", None) or str(msg.role)
                if role == "user":
                    latest_query = msg.text
                    break

        # Search with relevant context instead of generic query
        search_query = latest_query or "user preferences and history"
        print(f"Mem0Agent search query: {search_query}")
        results = await memory.search(user_id=username, query=search_query, limit=5)
        print(results)
        memories = results.get("results", []) if isinstance(results, dict) else []
        lines: list[str] = []
        for item in memories:
            if isinstance(item, dict):
                memory_text = item.get("memory") or item.get(
                    "text") or item.get("content")
                if memory_text:
                    lines.append(f"- {memory_text}")
        if not lines:
            return Context(messages=[])
        context_text = "Stored memories:\n" + "\n".join(lines)
        return Context(messages=[ChatMessage(role="system", text=context_text)])
