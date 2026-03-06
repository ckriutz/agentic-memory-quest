"""Reciprocal Rank Fusion (RRF) for hybrid retrieval.

Fuses ranked lists from sparse (BM25 / semantic) and dense (vector) signals
into a single ranking using the formula:

    score(doc) = Σ  1 / (k + rank_i)

where ``k`` is a configurable constant (default 60) and ``rank_i`` is the
1-based rank of the document in ranked list *i*.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from memory.config import RRF_K


def reciprocal_rank_fusion(
    *ranked_lists: List[Tuple[str, float]],
    k: int | None = None,
    top_k: int | None = None,
) -> List[Tuple[str, float]]:
    """Fuse multiple ranked lists via RRF.

    Each ranked list is a sequence of ``(doc_id, score)`` tuples **already
    sorted by score descending**.  The original scores are ignored; only
    ordinal ranks matter.

    Parameters
    ----------
    *ranked_lists:
        One or more ranked lists of ``(doc_id, score)`` pairs.
    k:
        RRF constant.  Higher values reduce the impact of high-ranked docs.
        Defaults to ``RRF_K`` from config (typically 60).
    top_k:
        Number of results to return.  ``None`` returns all.

    Returns
    -------
    List of ``(doc_id, rrf_score)`` sorted descending by RRF score.
    """
    if k is None:
        k = RRF_K

    scores: Dict[str, float] = {}

    for ranked in ranked_lists:
        for rank_0, (doc_id, _original_score) in enumerate(ranked):
            rank_1 = rank_0 + 1  # 1-based rank
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank_1)

    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    if top_k is not None:
        fused = fused[:top_k]

    return fused
