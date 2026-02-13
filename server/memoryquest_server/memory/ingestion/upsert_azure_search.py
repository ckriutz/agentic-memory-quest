"""Idempotent upsert to Azure AI Search for the cold ingestion path.

Uses deterministic document IDs (``sha256(tenant|user|agent|ts|hash)``) to
ensure the same logical event never creates duplicate documents.

Supports partial updates (merge) and emits structured metrics/logs.
Failed documents are routed to a Dead Letter Queue (DLQ) callback.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from memory import config as cfg

logger = logging.getLogger(__name__)

# Default DLQ handler — just logs.
_default_dlq: Callable[[Dict[str, Any]], None] = lambda doc: logger.error(
    "DLQ: document %s", doc.get("id", "unknown")
)


async def upsert_documents(
    documents: List[Dict[str, Any]],
    *,
    search_client: Any | None = None,
    dlq_handler: Callable[[Dict[str, Any]], None] | None = None,
    max_retries: int = 3,
) -> Dict[str, int]:
    """Upsert a batch of documents into Azure AI Search.

    Parameters
    ----------
    documents:
        List of dicts conforming to the index schema.  Each must have an ``id`` field.
    search_client:
        An initialised ``SearchClient``.  If ``None``, a new one is created from config.
    dlq_handler:
        Callback for permanently failed documents.
    max_retries:
        Exponential backoff retries on transient failures.

    Returns
    -------
    Dict with ``success`` and ``failed`` counts.
    """
    dlq = dlq_handler or _default_dlq

    if not documents:
        return {"success": 0, "failed": 0}

    client = search_client
    if client is None:
        if not cfg.AZURE_SEARCH_ENDPOINT or not cfg.AZURE_SEARCH_API_KEY:
            logger.warning("Search credentials not configured; routing %d docs to DLQ", len(documents))
            for doc in documents:
                dlq(doc)
            return {"success": 0, "failed": len(documents)}

        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=cfg.AZURE_SEARCH_ENDPOINT,
            index_name=cfg.MEMORY_INDEX_NAME,
            credential=AzureKeyCredential(cfg.AZURE_SEARCH_API_KEY),
        )

    # Ensure ts is ISO-8601 string.
    for doc in documents:
        if "ts" in doc and isinstance(doc["ts"], (int, float)):
            doc["ts"] = datetime.fromtimestamp(doc["ts"], tz=timezone.utc).isoformat()
        if "expires_at" in doc and isinstance(doc["expires_at"], (int, float)):
            doc["expires_at"] = datetime.fromtimestamp(
                doc["expires_at"], tz=timezone.utc
            ).isoformat()

    success = 0
    failed = 0
    import asyncio

    for attempt in range(max_retries):
        try:
            # merge_or_upload is idempotent: creates if absent, merges if present.
            results = client.merge_or_upload_documents(documents=documents)
            for result in results:
                if result.succeeded:
                    success += 1
                else:
                    failed += 1
                    matching = [d for d in documents if d.get("id") == result.key]
                    if matching:
                        dlq(matching[0])
            logger.info("upsert batch=%d success=%d failed=%d", len(documents), success, failed)
            return {"success": success, "failed": failed}
        except Exception:
            wait = 2**attempt
            logger.warning("Upsert attempt %d failed; retrying in %ds", attempt + 1, wait)
            await asyncio.sleep(wait)

    # All retries exhausted.
    for doc in documents:
        dlq(doc)
    logger.error("Upsert failed after %d retries; %d docs sent to DLQ", max_retries, len(documents))
    return {"success": 0, "failed": len(documents)}
