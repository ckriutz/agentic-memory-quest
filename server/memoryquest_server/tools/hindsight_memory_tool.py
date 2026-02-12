from typing import Any, MutableSequence, Sequence
import json
import os
import logging
from agent_framework import ChatMessage, Context, ContextProvider
from hindsight_client import Hindsight
from hindsight_client_api import DocumentsApi

logger = logging.getLogger(__name__)


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
    return "anonymous"


class HindsightMemoryTool(ContextProvider):
    def __init__(self) -> None:
        base_url = (os.getenv("HINDSIGHT_URL") or "http://localhost:8888").rstrip("/")
        self.client = Hindsight(base_url=base_url)
        print("Hindsight Memory Tool initialized")

    async def get_memories(self, username: str) -> Any:
        try:
            # Use a broader query to get a comprehensive view of the user
            return await self.client.areflect(
                bank_id=username,
                query="Generate a concise, factual profile of this user based on stored memories. Include preferences, specific details, and history. Do not use conversational language. Output as a structured summary.",
            )
        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return "Unable to retrieve memories at this time."

    async def get_regular_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
        api = DocumentsApi(self.client._api_client)
        docs = await api.list_documents(bank_id=username)
        return docs

    async def delete_user_memories(self, username: str) -> dict[str, Any]:
        api = DocumentsApi(self.client._api_client)
        result = await api.list_documents(bank_id=username)
        
        # Extract items from paginated response
        docs = result.items if hasattr(result, 'items') else result.get('items', [])
        
        ids = [doc.get("id") if isinstance(doc, dict) else doc.id for doc in docs]
        
        deleted_ids = []
        failed_deletions = []
        
        for doc_id in ids:
            try:
                # Actually await and log the delete operation
                delete_result = await api.delete_document(bank_id=username, document_id=doc_id)
                logger.info(f"Delete result for {doc_id}: {delete_result}")
                deleted_ids.append(doc_id)
            except Exception as e:
                logger.error(f"Failed to delete document {doc_id}: {e}")
                failed_deletions.append({"doc_id": doc_id, "error": str(e)})
        
        # Verify deletion by listing documents again
        verify_result = await api.list_documents(bank_id=username)
        verify_docs = verify_result.items if hasattr(verify_result, 'items') else verify_result.get('items', [])
        remaining_count = len(verify_docs)
        
        return {
            "deleted_ids": deleted_ids,
            "deleted_count": len(deleted_ids),
            "failed_deletions": failed_deletions,
            "remaining_documents": remaining_count,
            "actually_deleted": remaining_count == 0
        }

    async def invoked(self, request_messages: ChatMessage | Sequence[ChatMessage], response_messages: ChatMessage | Sequence[ChatMessage] | None = None, invoke_exception: Exception | None = None, **kwargs: Any,) -> None:
        print("HindsightMemoryTool invoked")
        username = _extract_username(request_messages, **kwargs)
        
        def _normalize_role(role: Any) -> str:
            return getattr(role, "value", None) or str(role)
        
        # Simplify message extraction
        messages: list[dict[str, str]] = []
        
        def _add_msgs(source: ChatMessage | Sequence[ChatMessage]):
            # Only retain user-provided content.
            # If we store assistant responses too, the assistant's own suggestions can be recalled later
            # and treated like user facts/preferences.
            if isinstance(source, ChatMessage):
                role = _normalize_role(source.role)
                if role == "user":
                    messages.append({"role": role, "content": source.text})
            else:
                for msg in source:
                    role = _normalize_role(msg.role)
                    if role == "user":
                        messages.append({"role": role, "content": msg.text})

        _add_msgs(request_messages)
        # Intentionally ignore response_messages (assistant output)

        try:
            content = json.dumps(messages, ensure_ascii=False)
            response = await self.client.aretain(bank_id=username, content=content)
            print("HindsightMemoryTool retain response:", response)
        except Exception as e:
            logger.error(f"Failed to save context to Hindsight: {e}")

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        print("HindsightMemoryTool invoking")
        username = _extract_username(messages, **kwargs)
        
        # Dynamic query based on the latest user message context
        query = "General user preferences and history"
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
            role = getattr(messages.role, "value", None) or str(messages.role)
            if role == "user" and len(messages.text) > 5:
                query = messages.text

        try:
            results = await self.client.arecall(
                bank_id=username,
                query=query,
            )
            print(f"HindsightMemoryTool recall results for '{query}':", results)

            return Context(
                messages=[
                    ChatMessage(
                        role="system",
                        text=f"Relevant memories recalled based on current conversation:\n{results}",
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Failed to recall memories: {e}")
            # Return empty context so the agent can still proceed without memory
            return Context(messages=[])