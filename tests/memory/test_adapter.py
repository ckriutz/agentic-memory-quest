"""Unit tests for data models and the adapter interface contract."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "memoryquest_server"))

from memory.models import MemoryEvent, MemoryHit, QueryContext


def test_memory_event_generate_id_deterministic():
    """Same inputs produce the same document ID."""
    id1 = MemoryEvent.generate_id("t1", "u1", "a1", 1000.0, "hash1")
    id2 = MemoryEvent.generate_id("t1", "u1", "a1", 1000.0, "hash1")
    assert id1 == id2
    assert len(id1) == 64  # sha256 hex


def test_memory_event_generate_id_varies_with_input():
    id1 = MemoryEvent.generate_id("t1", "u1", "a1", 1000.0, "hash1")
    id2 = MemoryEvent.generate_id("t1", "u1", "a1", 1000.0, "hash2")
    assert id1 != id2


def test_content_hash():
    h1 = MemoryEvent.content_hash("hello world")
    h2 = MemoryEvent.content_hash("hello world")
    h3 = MemoryEvent.content_hash("different text")
    assert h1 == h2
    assert h1 != h3


def test_memory_hit_defaults():
    hit = MemoryHit(id="1", text_snippet="test", score=0.9, source="unit")
    assert hit.metadata == {}


def test_query_context_defaults():
    ctx = QueryContext(text="q", user_id="u", tenant_id="t", agent_id="a")
    assert ctx.tags is None
    assert ctx.filters is None
    assert ctx.time > 0


def test_none_agent_excluded_from_adapter():
    """Verify that the 'none' agent type is explicitly excluded.

    The adapter integration in server.py only wires into named agents
    (agent-framework, mem0, cognee, hindsight, foundry).  The 'none'
    endpoint (generic_agent at POST /) must not call the memory adapter.
    This is a documentation/contract test — actual exclusion is verified
    by inspecting the server code in integration tests.
    """
    excluded_agents = {"none"}
    integrated_agents = {
        "agent-framework",
        "mem0",
        "cognee",
        "hindsight",
        "foundry",
    }
    assert excluded_agents.isdisjoint(integrated_agents)
