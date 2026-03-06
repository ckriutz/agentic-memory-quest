"""Data models for the HOT/COLD memory architecture."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryEvent:
    """An event produced by an agent to be ingested into the memory store."""

    id: str
    agent_id: str
    user_id: str
    tenant_id: str
    ts: float = field(default_factory=time.time)
    text: str = ""
    tool_outputs: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    pii_suspected: bool = False

    @staticmethod
    def generate_id(
        tenant_id: str,
        user_id: str,
        agent_id: str,
        ts: float,
        content_hash: str,
    ) -> str:
        """Deterministic document ID: sha256(tenant_id|user_id|agent_id|ts|content_hash)."""
        raw = f"{tenant_id}|{user_id}|{agent_id}|{ts}|{content_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class MemoryHit:
    """A single result from a memory retrieval query."""

    id: str
    text_snippet: str
    score: float
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryContext:
    """Context for a memory retrieval query."""

    text: str
    user_id: str
    tenant_id: str
    agent_id: str
    time: float = field(default_factory=time.time)
    tags: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
