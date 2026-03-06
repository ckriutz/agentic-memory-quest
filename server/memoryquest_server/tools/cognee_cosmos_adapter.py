"""Cognee VectorDBInterface implementation backed by Azure Cosmos DB for NoSQL.

This adapter lets Cognee store and query its knowledge-graph embeddings in
Azure Cosmos DB for NoSQL (with DiskANN vector indexing) instead of Qdrant
or Azure AI Search.

Design decisions
----------------
* Each *collection* becomes a Cosmos DB container with the prefix ``cognee-``
  inside the ``memquest-db`` database.
* Vector embeddings are stored as a ``/vector`` property on each document.
* The partition key is ``/collection`` for per-collection isolation.
* ``VectorDistance`` system function with cosine similarity is used for search.
* ``embed_data`` delegates to the ``embedding_engine`` supplied by Cognee.
* ``prune()`` only deletes containers that start with ``cognee-``.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional
from uuid import UUID

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

logger = logging.getLogger(__name__)

# ── Cognee types (imported at runtime to avoid hard-coupling) ────────
try:
    from cognee.infrastructure.databases.vector.models.ScoredResult import ScoredResult
except ImportError:
    from pydantic import BaseModel

    class ScoredResult(BaseModel):  # type: ignore[no-redef]
        id: UUID
        score: float
        payload: Optional[dict[str, Any]] = None

_DEFAULT_DIM = 1536
_DATABASE_NAME = "memquest-db"


class CogneeCosmosAdapter:
    """Drop-in replacement for Cognee's Qdrant / Azure AI Search vector adapter.

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

        self._client = CosmosClient(url=self.url, credential=self.api_key)
        self._db = self._client.get_database_client(_DATABASE_NAME)

    # ── helpers ──────────────────────────────────────────────────────

    def _sanitize_container_name(self, collection_name: str) -> str:
        """Cosmos container names: 3-63 chars, lowercase alphanumeric + hyphens."""
        raw = f"cognee-{self.database_name}-{collection_name}"
        sanitized = re.sub(r"[^a-z0-9\-]", "-", raw.lower())
        sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
        if len(sanitized) < 3:
            sanitized = f"cognee-{sanitized}"
        return sanitized[:63]

    def _get_dimension(self) -> int:
        if self.embedding_engine is not None:
            dim = getattr(self.embedding_engine, "dimension", None) or getattr(
                self.embedding_engine, "dimensions", None
            )
            if dim:
                return int(dim)
        return _DEFAULT_DIM

    def _get_container(self, container_name: str):
        return self._db.get_container_client(container_name)

    # ── VectorDBInterface: required methods ──────────────────────────

    async def has_collection(self, collection_name: str) -> bool:
        container_name = self._sanitize_container_name(collection_name)
        try:
            self._get_container(container_name).read()
            return True
        except CosmosResourceNotFoundError:
            return False
        except Exception:
            return False

    async def create_collection(
        self, collection_name: str, payload_schema: Any = None
    ) -> None:
        container_name = self._sanitize_container_name(collection_name)
        dim = self._get_dimension()
        try:
            # Create container with vector embedding policy for DiskANN
            vector_embedding_policy = {
                "vectorEmbeddings": [
                    {
                        "path": "/vector",
                        "dataType": "float32",
                        "distanceFunction": "cosine",
                        "dimensions": dim,
                    }
                ]
            }

            indexing_policy = {
                "indexingMode": "consistent",
                "automatic": True,
                "includedPaths": [{"path": "/*"}],
                "excludedPaths": [
                    {"path": "/_etag/?"},
                    {"path": "/vector/*"},
                ],
                "vectorIndexes": [
                    {"path": "/vector", "type": "diskANN"}
                ],
            }

            self._db.create_container_if_not_exists(
                id=container_name,
                partition_key=PartitionKey(path="/collection"),
                vector_embedding_policy=vector_embedding_policy,
                indexing_policy=indexing_policy,
            )
            logger.info("Cosmos container created/verified: %s", container_name)
        except Exception as exc:
            logger.error("Failed to create container %s: %s", container_name, exc)
            raise

    async def create_data_points(
        self, collection_name: str, data_points: list[Any]
    ) -> None:
        container_name = self._sanitize_container_name(collection_name)
        container = self._get_container(container_name)

        for dp in data_points:
            doc: dict[str, Any] = {
                "id": str(dp.id) if hasattr(dp, "id") else str(uuid.uuid4()),
                "collection": collection_name,
            }

            # Extract vector
            if hasattr(dp, "get_embeddable_data"):
                try:
                    vec = dp.get_embeddable_data()
                    if vec is not None:
                        doc["vector"] = list(vec)
                except Exception:
                    pass

            if "vector" not in doc:
                dump = dp.model_dump() if hasattr(dp, "model_dump") else {}
                vec = dump.get("_vector") or dump.get("vector")
                if vec is not None:
                    doc["vector"] = list(vec)

            # Text and payload
            text = ""
            if hasattr(dp, "model_dump"):
                dump = dp.model_dump()
                text = dump.get("text", "") or dump.get("content", "") or str(dump)
                # Store payload as a JSON string (Cosmos has 2MB doc limit)
                doc["payload"] = json.dumps(dump, default=str)
            else:
                doc["payload"] = json.dumps({"raw": str(dp)}, default=str)
                text = str(dp)

            doc["text"] = text[:32000] if text else ""

            try:
                container.upsert_item(doc)
            except Exception as exc:
                logger.error("Upsert to %s failed: %s", container_name, exc)
                raise

        logger.debug("Upserted %d docs to %s", len(data_points), container_name)

    async def retrieve(
        self, collection_name: str, data_point_ids: list[str]
    ) -> list[Any]:
        container_name = self._sanitize_container_name(collection_name)
        container = self._get_container(container_name)
        results: list[ScoredResult] = []

        for doc_id in data_point_ids:
            try:
                doc = container.read_item(item=str(doc_id), partition_key=collection_name)
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
        container_name = self._sanitize_container_name(collection_name)
        container = self._get_container(container_name)

        try:
            if query_vector:
                # Vector search using VectorDistance system function
                vector_str = json.dumps(query_vector)
                query = (
                    f"SELECT TOP {limit} c.id, c.text, c.payload, "
                    f"VectorDistance(c.vector, {vector_str}) AS score "
                    f"FROM c "
                    f"WHERE c.collection = @collection "
                    f"ORDER BY VectorDistance(c.vector, {vector_str})"
                )
                parameters = [{"name": "@collection", "value": collection_name}]
            elif query_text:
                # Text-based search (simple CONTAINS fallback)
                query = (
                    f"SELECT TOP {limit} c.id, c.text, c.payload "
                    f"FROM c "
                    f"WHERE c.collection = @collection "
                    f"AND CONTAINS(LOWER(c.text), LOWER(@query))"
                )
                parameters = [
                    {"name": "@collection", "value": collection_name},
                    {"name": "@query", "value": query_text[:200]},
                ]
            else:
                # Fallback: return recent documents
                query = (
                    f"SELECT TOP {limit} c.id, c.text, c.payload "
                    f"FROM c "
                    f"WHERE c.collection = @collection"
                )
                parameters = [{"name": "@collection", "value": collection_name}]

            items = list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                )
            )

            results: list[ScoredResult] = []
            for hit in items:
                doc_id = hit.get("id", str(uuid.uuid4()))
                score = hit.get("score", 0.0)
                payload = {}
                if hit.get("payload"):
                    try:
                        payload = json.loads(hit["payload"])
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": hit["payload"]}
                results.append(
                    ScoredResult(
                        id=UUID(str(doc_id)) if doc_id else uuid.uuid4(),
                        score=float(score) if score else 0.0,
                        payload=payload,
                    )
                )
            return results
        except Exception as exc:
            logger.error("Search in %s failed: %s", container_name, exc)
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
        container_name = self._sanitize_container_name(collection_name)
        container = self._get_container(container_name)
        for doc_id in data_point_ids:
            try:
                container.delete_item(item=str(doc_id), partition_key=collection_name)
            except Exception:
                continue
        logger.debug("Deleted %d docs from %s", len(data_point_ids), container_name)

    async def prune(self) -> None:
        """Delete all containers with the ``cognee-`` prefix."""
        try:
            for container_props in self._db.list_containers():
                name = container_props.get("id", "")
                if name.startswith("cognee-"):
                    self._db.delete_container(name)
                    logger.info("Pruned container: %s", name)
        except Exception as exc:
            logger.error("Prune failed: %s", exc)

    async def embed_data(self, data: list[Any]) -> list[list[float]]:
        """Embed a list of texts/data points using the injected embedding engine."""
        if self.embedding_engine is None:
            raise RuntimeError("No embedding_engine supplied to CogneeCosmosAdapter")
        texts = [str(d) for d in data]
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
        container_name = self._sanitize_container_name(collection_name)
        try:
            return self._get_container(container_name).read()
        except Exception:
            return None

    async def create_vector_index(self, index_name: str, index_property_name: str) -> None:
        pass  # Vector index is created in create_collection

    async def index_data_points(
        self, index_name: str, index_property_name: str, data_points: list[Any]
    ) -> None:
        await self.create_data_points(index_name, data_points)

    async def get_data_point_schema(self, data_point_type: type) -> dict[str, Any]:
        return {}

    async def get_collection_names(self) -> list[str]:
        try:
            return [
                props["id"]
                for props in self._db.list_containers()
                if props["id"].startswith("cognee-")
            ]
        except Exception:
            return []
