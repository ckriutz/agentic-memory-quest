"""Unit tests for memory decider heuristics."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "memoryquest_server"))

from memory.ingestion.memory_decider import decide, reset_seen_hashes


def setup_function():
    """Reset dedup cache before each test."""
    reset_seen_hashes()


def test_short_text_rejected():
    result = decide("hi")
    assert result.should_store is False
    assert result.reason == "too_short"


def test_chit_chat_rejected():
    # "thanks" is short enough to be rejected as too_short first; the
    # chit-chat check fires on exact matches after the length gate.
    result = decide("thanks")
    assert result.should_store is False
    assert result.reason in ("too_short", "chit_chat")


def test_meaningful_text_accepted():
    result = decide("I prefer a deep tissue massage at 9am every morning.")
    assert result.should_store is True
    assert result.reason == "heuristic_pass"


def test_duplicate_rejected():
    text = "I prefer ocean view rooms with a king bed."
    r1 = decide(text)
    assert r1.should_store is True
    r2 = decide(text)
    assert r2.should_store is False
    assert r2.reason == "duplicate"


def test_durable_tag_no_expiry():
    result = decide("I am allergic to peanuts.", tags=["preference"])
    assert result.should_store is True
    assert result.expires_at is None  # durable — no TTL


def test_volatile_item_gets_ttl():
    result = decide("The weather looks nice today for kayaking.")
    assert result.should_store is True
    assert result.expires_at is not None


def test_content_hash_populated():
    result = decide("Some meaningful sentence about my travel plans.")
    assert len(result.content_hash) == 64  # sha256 hex digest
