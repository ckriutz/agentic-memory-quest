"""Azure AI Search memory adapter — implements ``IMemoryAdapter``.

HOT path (``retrieve``):
    1. Compute query embedding.
    2. Hybrid retrieval: BM25 (sparse) + vector similarity (dense).
    3. Fuse via RRF.
    4. Optionally re-rank with Azure Semantic Ranker.
    5. Return top-K ``MemoryHit`` objects.

COLD path (``enqueue_write``):
    Non-blocking send to Event Hubs.

The adapter never performs writes on the hot path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Protocol

from memory import config as cfg
from memory.models import MemoryEvent, MemoryHit, QueryContext
from memory.retrieval.hybrid_rrf import reciprocal_rank_fusion
from memory.retrieval.semantic_ranker import rerank_with_semantic_ranker

logger = logging.getLogger(__name__)


# ── Interface (structural typing) ────────────────────────────────────

class IMemoryAdapter(Protocol):
    """Shared memory adapter interface."""

    async def retrieve(
        self,
        query: QueryContext,
        k: int = 8,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryHit]: ...

    async def enqueue_write(self, event: MemoryEvent) -> None: ...


# ── Implementation ───────────────────────────────────────────────────

class AzureSearchMemoryAdapter:
    """Production adapter backed by Azure AI Search + Event Hubs."""

    def __init__(self) -> None:
        self._search_client: Any | None = None
        self._index_client: Any | None = None
        self._embed_client: Any | None = None
        self._eventhub_producer: Any | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

    # -- Lazy initialisation (connection pooling) ----------------------

    async def _ensure_clients(self) -> None:
        """Lazily initialise SDK clients on first use."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            try:
                if cfg.AZURE_SEARCH_ENDPOINT and cfg.AZURE_SEARCH_API_KEY:
                    from azure.core.credentials import AzureKeyCredential
                    from azure.search.documents import SearchClient

                    credential = AzureKeyCredential(cfg.AZURE_SEARCH_API_KEY)
                    self._search_client = SearchClient(
                        endpoint=cfg.AZURE_SEARCH_ENDPOINT,
                        index_name=cfg.MEMORY_INDEX_NAME,
                        credential=credential,
                    )
                if cfg.EVENT_HUBS_CONN_STR and cfg.COLD_INGEST_ENABLED:
                    from azure.eventhub.aio import EventHubProducerClient

                    self._eventhub_producer = (
                        EventHubProducerClient.from_connection_string(
                            cfg.EVENT_HUBS_CONN_STR,
                            eventhub_name=cfg.EVENT_HUBS_NAME,
                        )
                    )
            except Exception:
                logger.exception("Failed to initialise memory adapter clients")
            self._initialized = True

    # -- HOT PATH (read-only) -----------------------------------------

    async def retrieve(
        self,
        query: QueryContext,
        k: int | None = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryHit]:
        """Hybrid BM25 + vector retrieval with RRF fusion.

        On any failure the method returns an empty list — the request must
        never fail because memory retrieval is unavailable.
        """
        if not cfg.MEMORY_ENABLED or not cfg.HOT_RETRIEVAL_ENABLED:
            return []

        k = k or cfg.MEMORY_K
        start = time.monotonic()

        try:
            await self._ensure_clients()
            if self._search_client is None:
                return []

            query_vector = await self._compute_embedding(query.text)

            # Build OData filter for tenant/user isolation.
            filter_parts: list[str] = []
            if query.tenant_id:
                filter_parts.append(f"tenant_id eq '{query.tenant_id}'")
            if query.user_id:
                filter_parts.append(f"user_id eq '{query.user_id}'")
            if filters:
                for fk, fv in filters.items():
                    filter_parts.append(f"{fk} eq '{fv}'")
            odata_filter = " and ".join(filter_parts) if filter_parts else None

            sparse_results = await self._sparse_search(query.text, odata_filter, k * 2)
            dense_results = await self._dense_search(query_vector, odata_filter, k * 2)

            fused = reciprocal_rank_fusion(sparse_results, dense_results, top_k=k)

            # Build candidate dicts for optional semantic re-ranking.
            id_to_text: Dict[str, str] = {}
            for doc_id, _score in sparse_results + dense_results:
                id_to_text.setdefault(doc_id, "")
            # We already have text from the searches cached on self._last_texts
            candidates = [
                {"id": doc_id, "text": self._last_texts.get(doc_id, ""), "rrf_score": score}
                for doc_id, score in fused
            ]

            reranked = rerank_with_semantic_ranker(
                candidates, query.text, search_client=self._search_client
            )

            hits: List[MemoryHit] = []
            for entry in reranked[:k]:
                hits.append(
                    MemoryHit(
                        id=entry["id"],
                        text_snippet=entry.get("text", ""),
                        score=entry.get("semantic_score", entry.get("rrf_score", 0.0)),
                        source="azure_search",
                        metadata=entry.get("metadata", {}),
                    )
                )

            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info("memory.retrieve k=%d hits=%d elapsed_ms=%.1f", k, len(hits), elapsed_ms)
            return hits

        except Exception:
            logger.exception("memory.retrieve failed; returning empty context")
            return []

    # -- COLD PATH (non-blocking write) --------------------------------

    async def enqueue_write(self, event: MemoryEvent) -> None:
        """Send a MemoryEvent to Event Hubs without blocking the caller."""
        if not cfg.MEMORY_ENABLED or not cfg.COLD_INGEST_ENABLED:
            return
        asyncio.get_event_loop().call_soon(
            lambda: asyncio.ensure_future(self._send_to_eventhub(event))
        )

    async def _send_to_eventhub(self, event: MemoryEvent) -> None:
        try:
            await self._ensure_clients()
            if self._eventhub_producer is None:
                logger.debug("Event Hubs producer not configured; dropping event %s", event.id)
                return

            from azure.eventhub import EventData

            payload = json.dumps(
                {
                    "id": event.id,
                    "agent_id": event.agent_id,
                    "user_id": event.user_id,
                    "tenant_id": event.tenant_id,
                    "ts": event.ts,
                    "text": event.text,
                    "tool_outputs": event.tool_outputs,
                    "tags": event.tags,
                    "pii_suspected": event.pii_suspected,
                }
            )

            batch = await self._eventhub_producer.create_batch(
                partition_key=event.tenant_id or event.user_id
            )
            batch.add(EventData(payload))
            await self._eventhub_producer.send_batch(batch)
            logger.info("memory.enqueue_write sent event_id=%s", event.id)
        except Exception:
            logger.exception("memory.enqueue_write failed for event_id=%s", event.id)

    # -- Internal helpers ─────────────────────────────────────────────

    async def _compute_embedding(self, text: str) -> List[float]:
        """Compute embedding for *text* using Azure OpenAI."""
        if not cfg.AZURE_OPENAI_ENDPOINT or not cfg.AZURE_OPENAI_API_KEY:
            return []
        try:
            from openai import AsyncAzureOpenAI

            if self._embed_client is None:
                self._embed_client = AsyncAzureOpenAI(
                    api_key=cfg.AZURE_OPENAI_API_KEY,
                    azure_endpoint=cfg.AZURE_OPENAI_ENDPOINT,
                    api_version="2024-02-01",
                )
            response = await self._embed_client.embeddings.create(
                input=[text], model=cfg.AZURE_OPENAI_EMBED_MODEL
            )
            return response.data[0].embedding
        except Exception:
            logger.exception("Embedding computation failed")
            return []

    # Cache for latest search results so semantic ranker can access text.
    _last_texts: Dict[str, str] = {}

    async def _sparse_search(
        self, text: str, odata_filter: str | None, top: int
    ) -> list[tuple[str, float]]:
        """BM25 text search via Azure AI Search."""
        try:
            results = self._search_client.search(
                search_text=text,
                filter=odata_filter,
                top=top,
                select=["id", "text", "metadata_json"],
            )
            ranked: list[tuple[str, float]] = []
            for doc in results:
                doc_id = doc["id"]
                self._last_texts[doc_id] = doc.get("text", "")
                ranked.append((doc_id, doc.get("@search.score", 0.0)))
            return ranked
        except Exception:
            logger.exception("Sparse search failed")
            return []

    async def _dense_search(
        self, vector: List[float], odata_filter: str | None, top: int
    ) -> list[tuple[str, float]]:
        """Vector similarity search via Azure AI Search."""
        if not vector:
            return []
        try:
            from azure.search.documents.models import VectorizedQuery

            vec_query = VectorizedQuery(
                vector=vector,
                k_nearest_neighbors=top,
                fields="vector",
            )
            results = self._search_client.search(
                search_text=None,
                vector_queries=[vec_query],
                filter=odata_filter,
                top=top,
                select=["id", "text", "metadata_json"],
            )
            ranked: list[tuple[str, float]] = []
            for doc in results:
                doc_id = doc["id"]
                self._last_texts[doc_id] = doc.get("text", "")
                ranked.append((doc_id, doc.get("@search.score", 0.0)))
            return ranked
        except Exception:
            logger.exception("Dense search failed")
            return []

    # -- Lifecycle -----------------------------------------------------

    async def close(self) -> None:
        """Shutdown Event Hubs producer gracefully."""
        if self._eventhub_producer is not None:
            try:
                await self._eventhub_producer.close()
            except Exception:
                pass
