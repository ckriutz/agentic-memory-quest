"""HOT/COLD memory architecture for agentic-memory-quest.

HOT path (read-only): Low-latency hybrid retrieval using Azure AI Search
    with BM25 + Vector search, combined with RRF, and optional Semantic Ranker.
COLD path (write/ingest): Asynchronous pipeline via Event Hubs → PII redaction
    → memory decider → embeddings → upsert to Azure AI Search.
"""

from memory.models import MemoryEvent, MemoryHit, QueryContext
from memory.adapter.azure_search_adapter import AzureSearchMemoryAdapter

__all__ = [
    "MemoryEvent",
    "MemoryHit",
    "QueryContext",
    "AzureSearchMemoryAdapter",
]
