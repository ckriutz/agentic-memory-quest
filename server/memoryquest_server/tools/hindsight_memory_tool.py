from typing import Any, MutableSequence, Sequence
import json
import os
from agent_framework import ChatMessage, Context, ContextProvider
from hindsight_client import Hindsight

class HindsightMemoryTool(ContextProvider):
    def __init__(self) -> None:
        base_url = (os.getenv("HINDSIGHT_URL") or "http://localhost:8888").rstrip("/")
        self.client = Hindsight(base_url=base_url)
        print("Hindsight Memory Tool initialized")

    async def get_memories(self, username: str) -> Any:
        return await self.client.areflect(
            bank_id=username,
            query="Tell me things you know about this user's spa preferences.",
        )

    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any,) -> None:
        print("HindsightMemoryTool invoked")
        username = kwargs.get("username") or "anonymous"
        # Implementation for storing or processing memories can be added here
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

        content = json.dumps(messages, ensure_ascii=False)
        response = await self.client.aretain(bank_id=username, content=content)
        print("HindsightMemoryTool retain response:", response)
        pass

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        print("HindsightMemoryTool invoking")
        username = kwargs.get("username") or "anonymous"
        results = await self.client.arecall(
            bank_id=username,
            query="Tell me things you know about this user's spa preferences.",
        )
        print("HindsightMemoryTool recall results:", results)

        return Context(
            messages=[
                ChatMessage(
                    role="system",
                    text=f"Hindsight memory recall results:\n{results}",
                )
            ]
        )