"""Optional Semantic Ranker re-ranking stage.

When ``AZURE_SEARCH_SEMANTIC_RANKER_ENABLED`` is true, the top-K candidates
from the RRF fusion are passed to the Azure AI Search Semantic Ranker for
final re-ordering.

This module provides a *local stub* for environments where the ranker is
disabled, and the real implementation when it is enabled.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from memory.config import (
    AZURE_SEARCH_SEMANTIC_CONFIG_NAME,
    AZURE_SEARCH_SEMANTIC_RANKER_ENABLED,
)

logger = logging.getLogger(__name__)


def rerank_with_semantic_ranker(
    candidates: List[Dict[str, Any]],
    query: str,
    *,
    search_client: Any | None = None,
    semantic_config: str | None = None,
) -> List[Dict[str, Any]]:
    """Re-rank *candidates* using the Azure AI Search Semantic Ranker.

    Parameters
    ----------
    candidates:
        List of dicts with at least ``id`` and ``text`` keys.
    query:
        The user query used for semantic relevance scoring.
    search_client:
        An initialised ``SearchClient`` instance.  If ``None`` or the
        feature flag is off, *candidates* are returned unchanged.
    semantic_config:
        Name of the semantic configuration on the index.

    Returns
    -------
    Re-ordered list of candidates (same shape).
    """
    if not AZURE_SEARCH_SEMANTIC_RANKER_ENABLED:
        return candidates

    if search_client is None:
        logger.warning("Semantic ranker enabled but no search_client provided; skipping.")
        return candidates

    config_name = semantic_config or AZURE_SEARCH_SEMANTIC_CONFIG_NAME

    try:
        doc_ids = [c["id"] for c in candidates]
        filter_expr = " or ".join(f"id eq '{did}'" for did in doc_ids)

        results = search_client.search(
            search_text=query,
            filter=filter_expr,
            query_type="semantic",
            semantic_configuration_name=config_name,
            top=len(candidates),
        )

        id_to_candidate = {c["id"]: c for c in candidates}
        reranked: List[Dict[str, Any]] = []
        for result in results:
            doc_id = result["id"]
            if doc_id in id_to_candidate:
                entry = id_to_candidate.pop(doc_id)
                entry["semantic_score"] = result.get("@search.reranker_score", 0.0)
                reranked.append(entry)

        # Append any candidates not returned by the ranker at the tail.
        reranked.extend(id_to_candidate.values())
        return reranked

    except Exception:
        logger.exception("Semantic ranker call failed; returning original ordering.")
        return candidates
