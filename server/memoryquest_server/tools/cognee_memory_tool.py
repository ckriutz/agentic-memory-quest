
import os
import cognee
from typing import Any, MutableSequence, Sequence
from cognee_community_vector_adapter_qdrant import register
from cognee_community_vector_adapter_qdrant.qdrant_adapter import QDrantAdapter
from qdrant_client import AsyncQdrantClient
from cognee.modules.data.exceptions.exceptions import DatasetNotFoundError
from agent_framework import ChatMessage, Context, ContextProvider
from dotenv import load_dotenv

load_dotenv()


class CustomQDrantAdapter(QDrantAdapter):
    """Custom QDrant adapter that properly handles HTTPS URLs.
    
    The default QDrantAdapter passes port=6333 even for HTTPS URLs, which causes
    connection issues. For HTTPS URLs, we must explicitly set port=443.
    Additionally, we need to strip any port already appended to the URL.
    """
    
    def get_qdrant_client(self) -> AsyncQdrantClient:
        if hasattr(self, 'qdrant_path') and self.qdrant_path is not None:
            return AsyncQdrantClient(path=self.qdrant_path)
        elif self.url is not None:
            url = self.url
            # Strip any port that may have been appended to the URL
            # (e.g., "https://example.com:6333" -> "https://example.com")
            if url.startswith("https://"):
                # Remove :port if present (pattern: https://host:port)
                import re
                url = re.sub(r':\d+/?$', '', url)
                url = url.rstrip('/')
                return AsyncQdrantClient(url=url, api_key=self.api_key, port=443)
            else:
                # For non-HTTPS URLs, use port 6333
                return AsyncQdrantClient(url=url, api_key=self.api_key, port=6333)
        
        return AsyncQdrantClient(location=":memory:")


class CogneeMemoryTool(ContextProvider):
    def __init__(self) -> None:
        print("Initializing Cognee Memory Tool")
        self.dataset_name = os.getenv("COGNEE_DATASET_NAME") or "main_dataset"
        self._configure_cognee()
        self._register_vector_adapter()

    def _dataset_name_for_user(self, username: str) -> str:
        safe_username = (username or "anonymous").strip() or "anonymous"
        return f"{self.dataset_name}__{safe_username}"

    def _extract_search_result_texts(self, results: Any) -> list[str]:
        texts: list[str] = []
        if results is None:
            return texts

        for result in results:
            search_result = None
            if isinstance(result, dict):
                search_result = result.get("search_result")
            else:
                search_result = getattr(result, "search_result", None)

            if search_result is None:
                continue

            if isinstance(search_result, list):
                texts.extend([str(x) for x in search_result])
            else:
                texts.append(str(search_result))

        return texts

    async def _dataset_exists(self, dataset_name: str) -> bool:
        try:
            datasets_api = cognee.datasets()
            datasets = await datasets_api.list_datasets()
            return any(getattr(ds, "name", None) == dataset_name for ds in datasets)
        except Exception:
            # If we can't reliably check, allow the search attempt.
            return True

    def _configure_cognee(self) -> None:
        """Configure cognee using environment variables from .env file."""
        # LLM Configuration - use the LLM_* variables directly from .env
        llm_endpoint = os.getenv("LLM_ENDPOINT")
        llm_api_key = os.getenv("LLM_API_KEY")
        llm_api_version = os.getenv("LLM_API_VERSION")
        llm_model = os.getenv("LLM_MODEL")
        
        # Embedding Configuration - use EMBEDDING_* variables directly from .env  
        embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT")
        embedding_api_key = os.getenv("EMBEDDING_API_KEY")
        embedding_api_version = os.getenv("EMBEDDING_API_VERSION")
        embedding_model = os.getenv("EMBEDDING_MODEL")
        embedding_dimensions = os.getenv("EMBEDDING_DIMENSIONS", "1536")
        
        # Vector DB Configuration - use VECTOR_DB_* variables directly from .env
        vector_db_url = os.getenv("VECTOR_DB_URL")
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
        
        print(
            f"Cognee configured: LLM={llm_model}, Embedding={embedding_model}, "
            f"VectorDB={vector_db_provider} at {vector_db_url}, dataset={self.dataset_name}"
        )

    def _register_vector_adapter(self) -> None:
        """Register our custom QDrant adapter that handles HTTPS properly."""
        try:
            register.use_vector_adapter("qdrant", CustomQDrantAdapter)
            print("Registered CustomQDrantAdapter for qdrant")
        except Exception as exc:
            print(f"Cognee Qdrant adapter register failed: {exc}")

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after the agent processes messages - stores conversation in cognee."""
        username = kwargs.get("username", "anonymous")
        print(f"CogneeMemoryTool invoked for user: {username}")

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

        content = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        print(f"Adding content to cognee: {content[:100]}...")

        dataset_name = self._dataset_name_for_user(username)

        result = await cognee.add(content, dataset_name=dataset_name)
        print(f"Cognee add result: {result}")

        # Process with LLMs to build the knowledge graph
        await cognee.cognify(datasets=dataset_name)
        print("Cognee cognify completed")

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage],**kwargs: Any,) -> Context:
        """Called before the agent processes messages - can inject context from cognee."""
        print("CogneeMemoryTool invoking")
        username = kwargs.get("username", "anonymous")
        dataset_name = self._dataset_name_for_user(username)

        results: Any = None

        try:
            if not await self._dataset_exists(dataset_name):
                memories = []
                return Context(
                    messages=[
                        ChatMessage(
                            role="system",
                            text=f"Cognee memory recall results:\n{memories}",
                        )
                    ]
                )

            results = await cognee.search(
                query_text=f"Can you tell me a little about the user {username} and their spa preferences?",
                datasets=dataset_name,
            )
            memories = self._extract_search_result_texts(results)
        except DatasetNotFoundError:
            memories = []
        
        print(f"Cognee search results: {results}")
        return Context(
            messages=[
                ChatMessage(
                    role="system",
                    text=f"Cognee memory recall results:\n{memories}",
                )
            ]
        )
    
    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[str]:
        """Retrieve memories for a given username from cognee."""
        print(f"Retrieving memories for user: {username}")
        
        # Use the query parameter if provided, otherwise ask about spa preferences
        search_query = query or f"Can you tell me a little about the user {username} and their spa preferences?"

        dataset_name = self._dataset_name_for_user(username)
        try:
            if not await self._dataset_exists(dataset_name):
                memories = []
                if limit and limit > 0:
                    return memories[:limit]
                return memories

            results = await cognee.search(query_text=search_query, datasets=dataset_name)
            memories = self._extract_search_result_texts(results)
        except DatasetNotFoundError:
            memories = []

        if limit and limit > 0:
            return memories[:limit]
        return memories

    async def delete_user_memories(self, username: str) -> dict[str, Any]:
        """Delete all stored Cognee memories for the given user.

        Implementation detail: we store each user's data in a separate dataset named
        `{base_dataset}__{username}`, so deleting the dataset deletes all of that user's data.
        """
        dataset_name = self._dataset_name_for_user(username)
        datasets_api = cognee.datasets()

        datasets = await datasets_api.list_datasets()
        dataset = next((ds for ds in datasets if getattr(ds, "name", None) == dataset_name), None)
        if dataset is None:
            return {
                "deleted": False,
                "dataset_name": dataset_name,
                "reason": "dataset_not_found",
            }

        dataset_id = getattr(dataset, "id", None)
        await datasets_api.delete_dataset(str(dataset_id))

        return {
            "deleted": True,
            "dataset_name": dataset_name,
            "dataset_id": str(dataset_id),
        }