
import os
import cognee
from typing import Any, MutableSequence, Sequence
from cognee_community_vector_adapter_qdrant import register
from cognee_community_vector_adapter_qdrant.qdrant_adapter import QDrantAdapter
from qdrant_client import AsyncQdrantClient
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
        self._configure_cognee()
        self._register_vector_adapter()

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
        embedding_dimensions = os.getenv("EMBEDDING_DIMENSIONS", "3072")
        
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
        
        print(f"Cognee configured: LLM={llm_model}, Embedding={embedding_model}, VectorDB={vector_db_provider} at {vector_db_url}")

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
        
        result = await cognee.add(content)
        print(f"Cognee add result: {result}")
    
        # Process with LLMs to build the knowledge graph
        await cognee.cognify()
        print("Cognee cognify completed")

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage],**kwargs: Any,) -> Context:
        """Called before the agent processes messages - can inject context from cognee."""
        print("CogneeMemoryTool invoking")
        results = await cognee.search(query_text=f"Can you tell me a little about the user {kwargs.get('username', 'anonymous')} and their spa preferences?")
        memories = []
        for result in results:
            if isinstance(result, dict) and 'search_result' in result:
                memories.extend(result['search_result'])
        
        print(f"Cognee search results: {results}")
        return Context(
            messages=[
                ChatMessage(
                    role="system",
                    text=f"Cognee memory recall results:\n{memories}",
                )
            ]
        )
    
    async def get_memories(self, username: str, query: str | None = None, limit: int = 10) -> list[dict[str, str]]:
        """Retrieve memories for a given username from cognee."""
        print(f"Retrieving memories for user: {username}")
        
        # Use the query parameter if provided, otherwise ask about spa preferences
        search_query = query or f"Can you tell me a little about the user {username} and their spa preferences?"
        
        results = await cognee.search(query_text=search_query)
        memories = []
        for result in results:
            if isinstance(result, dict) and 'search_result' in result:
                memories.extend(result['search_result'])
        
        return memories