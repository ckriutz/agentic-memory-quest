"""Cognee VectorDBInterface implementation backed by Azure AI Search.

This adapter lets Cognee store and query its knowledge-graph embeddings in
Azure AI Search instead of Qdrant.  Each *collection* becomes a separate
Azure Search index with the prefix ``cognee-`` so it cannot collide with
indexes created by other parts of the application (e.g. the HOT-path
``memquest-dev-memory`` index).

Design decisions
----------------
* ``database_name`` (the Cognee tenant / workspace) is encoded into the
  index name: ``cognee-{database_name}-{collection}``.
* HNSW with cosine similarity is used for the vector search configuration.
* ``prune()`` only deletes indexes that start with ``cognee-``.
* ``embed_data`` delegates to the ``embedding_engine`` supplied by Cognee's
  factory so the same model used everywhere else is reused.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional
from uuid import UUID

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)

# ── Cognee types (imported at runtime to avoid hard-coupling) ────────
try:
    from cognee.infrastructure.databases.vector.models.ScoredResult import ScoredResult
except ImportError:
    # Fallback – define a minimal compatible dataclass
    from pydantic import BaseModel

    class ScoredResult(BaseModel):  # type: ignore[no-redef]
        id: UUID
        score: float
        payload: Optional[dict[str, Any]] = None

# Dimension default – overridden dynamically when we have embedding_engine
_DEFAULT_DIM = 1536


class CogneeAzureSearchAdapter:
    """Drop-in replacement for Cognee's Qdrant vector adapter.

    Constructor signature matches the factory call in
    ``cognee.infrastructure.databases.vector.create_vector_engine``:

        adapter(url=..., api_key=..., embedding_engine=..., database_name=...)
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        embedding_engine: Any = None,
        database_name: str = "default",
    ) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.embedding_engine = embedding_engine
        self.database_name = database_name

        self._credential = AzureKeyCredential(api_key)
        self._index_client = SearchIndexClient(
            endpoint=self.url,
            credential=self._credential,
        )

    # ── helpers ──────────────────────────────────────────────────────

    def _sanitize_index_name(self, collection_name: str) -> str:
        """Azure Search index names: lowercase alphanumeric + hyphens, 2-128 chars."""
        raw = f"cognee-{self.database_name}-{collection_name}"
        sanitized = re.sub(r"[^a-z0-9\-]", "-", raw.lower())
        sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
        return sanitized[:128] if len(sanitized) >= 2 else f"cognee-{sanitized}"

    def _get_dimension(self) -> int:
        if self.embedding_engine is not None:
            dim = getattr(self.embedding_engine, "dimension", None) or getattr(
                self.embedding_engine, "dimensions", None
            )
            if dim:
                return int(dim)
        return _DEFAULT_DIM

    def _search_client(self, index_name: str) -> SearchClient:
        return SearchClient(
            endpoint=self.url,
            index_name=index_name,
            credential=self._credential,
        )

    def _build_index_schema(self, index_name: str, vector_size: int) -> SearchIndex:
        fields = [
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SearchableField(
                name="text",
                type=SearchFieldDataType.String,
            ),
            SearchField(
                name="vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=vector_size,
                vector_search_profile_name="cognee-hnsw-profile",
            ),
            SimpleField(
                name="payload",
                type=SearchFieldDataType.String,
                filterable=False,
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(name="cognee-hnsw-algo"),
            ],
            profiles=[
                VectorSearchProfile(
                    name="cognee-hnsw-profile",
                    algorithm_configuration_name="cognee-hnsw-algo",
                ),
            ],
        )

        return SearchIndex(
            name=index_name,
            fields=fields,
            vector_search=vector_search,
        )

    # ── VectorDBInterface: required methods ──────────────────────────

    async def has_collection(self, collection_name: str) -> bool:
        index_name = self._sanitize_index_name(collection_name)
        try:
            self._index_client.get_index(index_name)
            return True
        except Exception:
            return False

    async def create_collection(
        self, collection_name: str, payload_schema: Any = None
    ) -> None:
        index_name = self._sanitize_index_name(collection_name)
        vector_size = self._get_dimension()
        schema = self._build_index_schema(index_name, vector_size)
        try:
            self._index_client.create_or_update_index(schema)
            logger.info("Azure Search index created/updated: %s", index_name)
        except Exception as exc:
            logger.error("Failed to create index %s: %s", index_name, exc)
            raise

    async def create_data_points(
        self, collection_name: str, data_points: list[Any]
    ) -> None:
        index_name = self._sanitize_index_name(collection_name)
        client = self._search_client(index_name)

        import json

        docs: list[dict[str, Any]] = []
        for dp in data_points:
            doc: dict[str, Any] = {
                "id": str(dp.id) if hasattr(dp, "id") else str(uuid.uuid4()),
            }

            # Extract vector
            if hasattr(dp, "get_embeddable_data"):
                try:
                    vec = dp.get_embeddable_data()
                    if vec is not None:
                        doc["vector"] = list(vec)
                except Exception:
                    pass

            # If data_point was embedded already (common path)
            if "vector" not in doc:
                dump = dp.model_dump() if hasattr(dp, "model_dump") else {}
                vec = dump.get("_vector") or dump.get("vector")
                if vec is not None:
                    doc["vector"] = list(vec)

            # Text payload
            text = ""
            if hasattr(dp, "model_dump"):
                dump = dp.model_dump()
                text = dump.get("text", "") or dump.get("content", "") or str(dump)
                doc["payload"] = json.dumps(dump, default=str)
            else:
                doc["payload"] = json.dumps({"raw": str(dp)}, default=str)
                text = str(dp)

            doc["text"] = text[:32766] if text else ""

            docs.append(doc)

        if docs:
            try:
                client.upload_documents(documents=docs)
                logger.debug("Uploaded %d docs to %s", len(docs), index_name)
            except Exception as exc:
                logger.error("Upload to %s failed: %s", index_name, exc)
                raise

    async def retrieve(
        self, collection_name: str, data_point_ids: list[str]
    ) -> list[Any]:
        index_name = self._sanitize_index_name(collection_name)
        client = self._search_client(index_name)
        results: list[ScoredResult] = []
        for doc_id in data_point_ids:
            try:
                doc = client.get_document(key=str(doc_id))
                import json

                payload = json.loads(doc.get("payload", "{}")) if doc.get("payload") else {}
                results.append(
                    ScoredResult(
                        id=UUID(str(doc_id)),
                        score=1.0,
                        payload=payload,
                    )
                )
            except Exception:
                continue
        return results

    async def search(
        self,
        collection_name: str,
        query_text: str | None = None,
        query_vector: list[float] | None = None,
        limit: int = 10,
        with_vector: bool = False,
    ) -> list[ScoredResult]:
        index_name = self._sanitize_index_name(collection_name)
        client = self._search_client(index_name)

        vector_queries = None
        if query_vector:
            vector_queries = [
                VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=limit,
                    fields="vector",
                )
            ]

        try:
            response = client.search(
                search_text=query_text or "*",
                vector_queries=vector_queries,
                top=limit,
            )
            results: list[ScoredResult] = []
            import json

            for hit in response:
                doc_id = hit.get("id", str(uuid.uuid4()))
                score = hit.get("@search.score", 0.0)
                payload = {}
                if hit.get("payload"):
                    try:
                        payload = json.loads(hit["payload"])
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": hit["payload"]}
                results.append(
                    ScoredResult(
                        id=UUID(str(doc_id)) if doc_id else uuid.uuid4(),
                        score=float(score),
                        payload=payload,
                    )
                )
            return results
        except Exception as exc:
            logger.error("Search in %s failed: %s", index_name, exc)
            return []

    async def batch_search(
        self,
        collection_name: str,
        query_texts: list[str],
        limit: int = 10,
    ) -> list[list[ScoredResult]]:
        all_results: list[list[ScoredResult]] = []
        for query in query_texts:
            results = await self.search(
                collection_name=collection_name,
                query_text=query,
                limit=limit,
            )
            all_results.append(results)
        return all_results

    async def delete_data_points(
        self, collection_name: str, data_point_ids: list[str]
    ) -> None:
        index_name = self._sanitize_index_name(collection_name)
        client = self._search_client(index_name)
        docs_to_delete = [{"id": str(did)} for did in data_point_ids]
        try:
            client.delete_documents(documents=docs_to_delete)
            logger.debug(
                "Deleted %d docs from %s", len(docs_to_delete), index_name
            )
        except Exception as exc:
            logger.error("Delete from %s failed: %s", index_name, exc)

    async def prune(self) -> None:
        """Delete all indexes with the ``cognee-`` prefix."""
        try:
            for idx in self._index_client.list_indexes():
                if idx.name.startswith("cognee-"):
                    self._index_client.delete_index(idx.name)
                    logger.info("Pruned index: %s", idx.name)
        except Exception as exc:
            logger.error("Prune failed: %s", exc)

    async def embed_data(self, data: list[Any]) -> list[list[float]]:
        """Embed a list of texts/data points using the injected embedding engine."""
        if self.embedding_engine is None:
            raise RuntimeError("No embedding_engine supplied to CogneeAzureSearchAdapter")
        texts = [str(d) for d in data]
        # Cognee embedding engines expose .embed() or .embed_text()
        if hasattr(self.embedding_engine, "embed"):
            return await self.embedding_engine.embed(texts)
        elif hasattr(self.embedding_engine, "embed_text"):
            return await self.embedding_engine.embed_text(texts)
        else:
            raise RuntimeError(
                f"embedding_engine {type(self.embedding_engine)} has no embed() or embed_text() method"
            )

    # ── VectorDBInterface: optional methods (safe no-ops) ────────────

    async def get_connection(self) -> None:
        return None

    async def get_collection(self, collection_name: str) -> Any:
        index_name = self._sanitize_index_name(collection_name)
        try:
            return self._index_client.get_index(index_name)
        except Exception:
            return None

    async def create_vector_index(self, index_name: str, index_property_name: str) -> None:
        pass  # Index is created in create_collection

    async def index_data_points(
        self, index_name: str, index_property_name: str, data_points: list[Any]
    ) -> None:
        await self.create_data_points(index_name, data_points)

    async def get_data_point_schema(self, data_point_type: type) -> dict[str, Any]:
        return {}

    async def get_collection_names(self) -> list[str]:
        try:
            return [
                idx.name
                for idx in self._index_client.list_indexes()
                if idx.name.startswith("cognee-")
            ]
        except Exception:
            return []
