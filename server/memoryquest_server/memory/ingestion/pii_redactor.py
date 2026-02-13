"""PII Redactor for the cold ingestion path.

Provides configurable regex-based PII detection and masking.
Supports *mask*, *drop*, and *tag* modes via ``PII_REDACTION_MODE``.

Designed to be lightweight (regex-only by default) with a pluggable
interface for external providers (e.g. Presidio).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from memory.config import PII_REDACTION_ENABLED, PII_REDACTION_MODE

# ── Default patterns ─────────────────────────────────────────────────

_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


@dataclass
class RedactionResult:
    text: str
    pii_detected: bool
    pii_types: List[str]


def redact(text: str, *, mode: str | None = None) -> RedactionResult:
    """Apply PII redaction to *text*.

    Parameters
    ----------
    text:
        The raw input text.
    mode:
        Override for ``PII_REDACTION_MODE``.
        ``mask``  → replace matches with ``[REDACTED:<TYPE>]``.
        ``drop``  → replace matches with empty string.
        ``tag``   → leave text intact but flag ``pii_detected``.
    """
    if not PII_REDACTION_ENABLED:
        return RedactionResult(text=text, pii_detected=False, pii_types=[])

    mode = mode or PII_REDACTION_MODE
    pii_types: List[str] = []
    result_text = text

    for pii_type, pattern in _PATTERNS:
        if pattern.search(result_text):
            pii_types.append(pii_type)
            if mode == "mask":
                result_text = pattern.sub(f"[REDACTED:{pii_type}]", result_text)
            elif mode == "drop":
                result_text = pattern.sub("", result_text)
            # mode == "tag": no text modification

    return RedactionResult(
        text=result_text,
        pii_detected=bool(pii_types),
        pii_types=pii_types,
    )
