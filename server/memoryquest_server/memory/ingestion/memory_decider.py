"""Memory Decider — classifies whether a memory event is worth storing.

Heuristics (default):
- Drop very short / low-signal chit-chat (< ``MIN_TEXT_LENGTH`` chars).
- Keep events tagged with durable knowledge markers.
- De-duplicate via content hash.
- Assign TTL (``expires_at``) for volatile items.

Optional LLM-assisted classifier behind ``MEMORY_DECIDER_LLM_ENABLED``.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Optional, Set

from memory.config import MEMORY_DECIDER_LLM_ENABLED

# ── Tunables ─────────────────────────────────────────────────────────

MIN_TEXT_LENGTH = 15
DEFAULT_TTL_DAYS = 30
DURABLE_TAGS = frozenset(
    {
        "preference",
        "constraint",
        "decision",
        "tool_outcome",
        "task_state",
        "fact",
        "final_answer",
    }
)
CHIT_CHAT_PATTERNS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "ok",
        "okay",
        "thanks",
        "thank you",
        "bye",
        "yes",
        "no",
        "sure",
        "cool",
    }
)


@dataclass
class DecisionResult:
    should_store: bool
    reason: str
    expires_at: Optional[float] = None
    content_hash: str = ""


# Keep an in-memory set of recent content hashes for dedup.
_seen_hashes: Set[str] = set()
_MAX_SEEN = 50_000


def decide(
    text: str,
    tags: list[str] | None = None,
) -> DecisionResult:
    """Decide whether *text* should be persisted to long-term memory."""
    content_hash = hashlib.sha256(text.encode()).hexdigest()

    # De-duplication
    if content_hash in _seen_hashes:
        return DecisionResult(
            should_store=False, reason="duplicate", content_hash=content_hash
        )

    # Track hash (bounded LRU-style eviction)
    if len(_seen_hashes) >= _MAX_SEEN:
        _seen_hashes.clear()
    _seen_hashes.add(content_hash)

    stripped = text.strip().lower()

    # Too short
    if len(stripped) < MIN_TEXT_LENGTH:
        return DecisionResult(
            should_store=False, reason="too_short", content_hash=content_hash
        )

    # Chit-chat
    if stripped in CHIT_CHAT_PATTERNS:
        return DecisionResult(
            should_store=False, reason="chit_chat", content_hash=content_hash
        )

    # Durable tags get indefinite storage.
    tags_set = set(tags or [])
    is_durable = bool(tags_set & DURABLE_TAGS)

    expires_at: Optional[float] = None
    if not is_durable:
        expires_at = time.time() + DEFAULT_TTL_DAYS * 86_400

    # Optional LLM-assisted path (stub — implement with real LLM call when enabled).
    if MEMORY_DECIDER_LLM_ENABLED:
        # Future: call LLM to classify.  For now, fall through to heuristic.
        pass

    return DecisionResult(
        should_store=True,
        reason="heuristic_pass",
        expires_at=expires_at,
        content_hash=content_hash,
    )


def reset_seen_hashes() -> None:
    """Clear the dedup cache (useful for testing)."""
    _seen_hashes.clear()
