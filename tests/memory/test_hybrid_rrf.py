"""Unit tests for RRF fusion logic."""

import sys
import os

# Ensure the server source is importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "memoryquest_server"))

from memory.retrieval.hybrid_rrf import reciprocal_rank_fusion


def test_single_list_preserves_order():
    """A single ranked list should retain its original order."""
    ranked = [("doc_a", 10.0), ("doc_b", 8.0), ("doc_c", 5.0)]
    result = reciprocal_rank_fusion(ranked, k=60)
    ids = [doc_id for doc_id, _ in result]
    assert ids == ["doc_a", "doc_b", "doc_c"]


def test_two_lists_same_order():
    """When both lists agree on order, top doc stays top."""
    sparse = [("d1", 9.0), ("d2", 7.0), ("d3", 5.0)]
    dense = [("d1", 0.95), ("d2", 0.80), ("d3", 0.60)]
    result = reciprocal_rank_fusion(sparse, dense, k=60)
    assert result[0][0] == "d1"


def test_two_lists_disagreement():
    """When lists disagree, the doc appearing in both is boosted."""
    sparse = [("a", 10.0), ("b", 5.0)]
    dense = [("b", 0.99), ("c", 0.50)]
    result = reciprocal_rank_fusion(sparse, dense, k=60)
    # 'b' appears in both lists so should be ranked first.
    assert result[0][0] == "b"


def test_top_k_limits_output():
    ranked = [("d1", 3.0), ("d2", 2.0), ("d3", 1.0)]
    result = reciprocal_rank_fusion(ranked, top_k=2, k=60)
    assert len(result) == 2


def test_empty_lists():
    result = reciprocal_rank_fusion(k=60)
    assert result == []


def test_rrf_scores_are_deterministic():
    sparse = [("x", 1.0), ("y", 0.5)]
    dense = [("y", 0.9), ("x", 0.1)]
    r1 = reciprocal_rank_fusion(sparse, dense, k=60)
    r2 = reciprocal_rank_fusion(sparse, dense, k=60)
    assert r1 == r2


def test_ties_handled():
    """Docs with identical RRF scores should both appear."""
    # Two lists, each has the other's doc at rank 1 and 2 respectively.
    list1 = [("a", 1.0), ("b", 0.5)]
    list2 = [("b", 1.0), ("a", 0.5)]
    result = reciprocal_rank_fusion(list1, list2, k=60)
    # Both should have the same score.
    assert len(result) == 2
    assert result[0][1] == result[1][1]
