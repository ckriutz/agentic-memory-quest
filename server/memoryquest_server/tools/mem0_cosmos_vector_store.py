"""Custom Mem0-compatible vector store backed by Azure Cosmos DB for NoSQL.

Mem0 does not ship a native Cosmos DB vector store provider.  This module
implements the interface that ``mem0.vector_stores`` expects so it can be
injected via the ``client`` config key, letting Mem0 store and search
embeddings in Cosmos DB with DiskANN vector indexing.

Usage in Mem0 config::

    from tools.mem0_cosmos_vector_store import Mem0CosmosVectorStore

    store = Mem0CosmosVectorStore(
        cosmos_endpoint="https://...",
        cosmos_key="...",
        collection_name="mem0-vectors",
        embedding_model_dims=1536,
    )
    config = {
        "vector_store": {
            "provider": "qdrant",  # any provider — overridden by client
            "config": {
                "client": store,
                "collection_name": "mem0-vectors",
                "embedding_model_dims": 1536,
            },
        },
        ...
    }
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

logger = logging.getLogger(__name__)

_DATABASE_NAME = "memquest-db"
_CONTAINER_NAME = "mem0-vectors"


class Mem0CosmosVectorStore:
    """Cosmos DB NoSQL vector store that implements the Mem0 vector store interface.

    The Mem0 vector store interface expects these methods:
    - create_col(name, vector_size, distance)
    - insert(name, vectors, payloads, ids)
    - search(name, query, limit, filters)
    - delete(name, vector_id)
    - update(name, vector_id, vector, payload)
    - get(name, vector_id)
    - list_cols()
    - delete_col(name)
    - col_info(name)
    """

    def __init__(
        self,
        cosmos_endpoint: str,
        cosmos_key: str,
        collection_name: str = _CONTAINER_NAME,
        embedding_model_dims: int = 1536,
    ) -> None:
        self.cosmos_endpoint = cosmos_endpoint
        self.cosmos_key = cosmos_key
        self.collection_name = collection_name
        self.embedding_model_dims = embedding_model_dims

        self._client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key)
        self._db = self._client.get_database_client(_DATABASE_NAME)
        self._containers: dict[str, Any] = {}

    def _get_container(self, name: str):
        if name not in self._containers:
            self._containers[name] = self._db.get_container_client(name)
        return self._containers[name]

    def _ensure_container(self, name: str, vector_size: int = 1536):
        """Create or verify the container with vector embedding policy."""
        try:
            vector_embedding_policy = {
                "vectorEmbeddings": [
                    {
                        "path": "/vector",
                        "dataType": "float32",
                        "distanceFunction": "cosine",
                        "dimensions": vector_size,
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

            container = self._db.create_container_if_not_exists(
                id=name,
                partition_key=PartitionKey(path="/user_id"),
                vector_embedding_policy=vector_embedding_policy,
                indexing_policy=indexing_policy,
            )
            self._containers[name] = container
            return container
        except Exception as exc:
            logger.warning("Container ensure failed (may already exist): %s", exc)
            return self._get_container(name)

    # ── Mem0 vector store interface ──────────────────────────────────

    def create_col(self, name: str, vector_size: int, distance: str = "cosine") -> None:
        """Create a collection (Cosmos container) with vector embedding policy."""
        self._ensure_container(name, vector_size)
        logger.info("Cosmos container created/verified: %s (dims=%d)", name, vector_size)

    def insert(
        self,
        name: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """Insert vectors with optional payloads."""
        container = self._get_container(name)
        result_ids: list[str] = []

        for i, vector in enumerate(vectors):
            doc_id = ids[i] if ids and i < len(ids) else str(uuid.uuid4())
            payload = payloads[i] if payloads and i < len(payloads) else {}
            user_id = payload.get("user_id", "default")

            doc = {
                "id": doc_id,
                "vector": vector,
                "user_id": user_id,
                "payload": json.dumps(payload, default=str),
                "text": payload.get("data", "") or payload.get("text", "") or payload.get("memory", ""),
            }

            try:
                container.upsert_item(doc)
                result_ids.append(doc_id)
            except Exception as exc:
                logger.error("Insert to %s failed for doc %s: %s", name, doc_id, exc)

        return result_ids

    def search(
        self,
        name: str,
        query: list[float],
        limit: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Vector search using VectorDistance."""
        container = self._get_container(name)

        vector_str = json.dumps(query)

        # Build filter clause
        filter_clause = ""
        parameters = []
        if filters and "user_id" in filters:
            filter_clause = "AND c.user_id = @user_id"
            parameters.append({"name": "@user_id", "value": filters["user_id"]})

        sql = (
            f"SELECT TOP {limit} c.id, c.text, c.payload, c.user_id, "
            f"VectorDistance(c.vector, {vector_str}) AS score "
            f"FROM c "
            f"WHERE 1=1 {filter_clause} "
            f"ORDER BY VectorDistance(c.vector, {vector_str})"
        )

        try:
            items = list(
                container.query_items(
                    query=sql,
                    parameters=parameters if parameters else None,
                    enable_cross_partition_query=True,
                )
            )

            results: list[dict[str, Any]] = []
            for item in items:
                payload = {}
                if item.get("payload"):
                    try:
                        payload = json.loads(item["payload"])
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": item["payload"]}

                results.append({
                    "id": item["id"],
                    "score": float(item.get("score", 0.0)),
                    "payload": payload,
                })

            return results
        except Exception as exc:
            logger.error("Search in %s failed: %s", name, exc)
            return []

    def delete(self, name: str, vector_id: str) -> None:
        """Delete a single document by ID."""
        container = self._get_container(name)
        try:
            # We need to find the partition key value for this doc
            items = list(container.query_items(
                query="SELECT c.user_id FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": vector_id}],
                enable_cross_partition_query=True,
            ))
            if items:
                container.delete_item(item=vector_id, partition_key=items[0]["user_id"])
        except Exception as exc:
            logger.error("Delete from %s failed for %s: %s", name, vector_id, exc)

    def update(
        self,
        name: str,
        vector_id: str,
        vector: list[float] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Update a vector/payload by ID."""
        container = self._get_container(name)
        try:
            # Find the document first
            items = list(container.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": vector_id}],
                enable_cross_partition_query=True,
            ))
            if not items:
                return

            doc = items[0]
            if vector is not None:
                doc["vector"] = vector
            if payload is not None:
                doc["payload"] = json.dumps(payload, default=str)
                doc["text"] = payload.get("data", "") or payload.get("text", "") or payload.get("memory", "")
                doc["user_id"] = payload.get("user_id", doc.get("user_id", "default"))

            container.upsert_item(doc)
        except Exception as exc:
            logger.error("Update in %s failed for %s: %s", name, vector_id, exc)

    def get(self, name: str, vector_id: str) -> dict[str, Any] | None:
        """Get a single document by ID."""
        container = self._get_container(name)
        try:
            items = list(container.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": vector_id}],
                enable_cross_partition_query=True,
            ))
            if not items:
                return None
            doc = items[0]
            payload = {}
            if doc.get("payload"):
                try:
                    payload = json.loads(doc["payload"])
                except (json.JSONDecodeError, TypeError):
                    payload = {"raw": doc["payload"]}
            return {
                "id": doc["id"],
                "payload": payload,
                "vector": doc.get("vector"),
            }
        except Exception:
            return None

    def list_cols(self) -> list[dict[str, Any]]:
        """List all containers."""
        try:
            return [
                {"name": props["id"]}
                for props in self._db.list_containers()
            ]
        except Exception:
            return []

    def delete_col(self, name: str) -> None:
        """Delete an entire container."""
        try:
            self._db.delete_container(name)
            self._containers.pop(name, None)
        except Exception as exc:
            logger.error("Delete container %s failed: %s", name, exc)

    def col_info(self, name: str) -> dict[str, Any]:
        """Get container info."""
        try:
            props = self._get_container(name).read()
            return {"name": name, "vectors_count": 0, "status": "ok", "props": str(props.get("id", ""))}
        except Exception:
            return {"name": name, "vectors_count": 0, "status": "not_found"}

    def list(
        self,
        name: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[list[dict[str, Any]]]:
        """List vectors with optional filters. Returns [[results]]."""
        container = self._get_container(name)

        filter_clause = ""
        parameters = []
        if filters and "user_id" in filters:
            filter_clause = "WHERE c.user_id = @user_id"
            parameters.append({"name": "@user_id", "value": filters["user_id"]})

        sql = f"SELECT TOP {limit} c.id, c.text, c.payload, c.user_id FROM c {filter_clause}"

        try:
            items = list(
                container.query_items(
                    query=sql,
                    parameters=parameters if parameters else None,
                    enable_cross_partition_query=True,
                )
            )
            results: list[dict[str, Any]] = []
            for item in items:
                payload = {}
                if item.get("payload"):
                    try:
                        payload = json.loads(item["payload"])
                    except (json.JSONDecodeError, TypeError):
                        payload = {"raw": item["payload"]}
                results.append({
                    "id": item["id"],
                    "payload": payload,
                })
            return [results]
        except Exception as exc:
            logger.error("List in %s failed: %s", name, exc)
            return [[]]
