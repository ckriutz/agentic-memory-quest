"""Centralised configuration for the memory layer.

All values are read from environment variables with sensible defaults.
Feature flags allow enabling/disabling HOT and COLD paths independently.
"""

from __future__ import annotations

import os


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("true", "1", "yes")


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ── Core ─────────────────────────────────────────────────────────────
MEMORY_ENABLED: bool = _bool_env("MEMORY_ENABLED", True)
MEMORY_INDEX_NAME: str = os.getenv(
    "MEMORY_INDEX_NAME",
    f"{os.getenv('APP_NAME', 'memquest')}-{os.getenv('ENV', 'dev')}-memory",
)
MEMORY_K: int = _int_env("MEMORY_K", 8)

# ── Azure AI Search ──────────────────────────────────────────────────
AZURE_SEARCH_ENDPOINT: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
AZURE_SEARCH_API_KEY: str = os.getenv("AZURE_SEARCH_API_KEY", "")
AZURE_SEARCH_SEMANTIC_RANKER_ENABLED: bool = _bool_env(
    "AZURE_SEARCH_SEMANTIC_RANKER_ENABLED", False
)
AZURE_SEARCH_SEMANTIC_CONFIG_NAME: str = os.getenv(
    "AZURE_SEARCH_SEMANTIC_CONFIG_NAME", "default"
)
AZURE_SEARCH_VECTOR_DIM: int = _int_env("AZURE_SEARCH_VECTOR_DIM", 1536)

# ── HOT / COLD feature flags ────────────────────────────────────────
HOT_RETRIEVAL_ENABLED: bool = _bool_env("HOT_RETRIEVAL_ENABLED", True)
COLD_INGEST_ENABLED: bool = _bool_env("COLD_INGEST_ENABLED", True)

# ── Event Hubs ───────────────────────────────────────────────────────
EVENT_HUBS_CONN_STR: str = os.getenv("EVENT_HUBS_CONN_STR", "")
EVENT_HUBS_NAME: str = os.getenv("EVENT_HUBS_NAME", "memory-events")
EVENT_HUBS_CONSUMER_GROUP: str = os.getenv(
    "EVENT_HUBS_CONSUMER_GROUP", "$Default"
)

# ── Embeddings ───────────────────────────────────────────────────────
EMBEDDINGS_PROVIDER: str = os.getenv("EMBEDDINGS_PROVIDER", "azure_openai")
AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_EMBED_MODEL: str = os.getenv(
    "AZURE_OPENAI_EMBED_MODEL", "text-embedding-3-large"
)

# ── PII ──────────────────────────────────────────────────────────────
PII_REDACTION_ENABLED: bool = _bool_env("PII_REDACTION_ENABLED", True)
PII_REDACTION_MODE: str = os.getenv("PII_REDACTION_MODE", "mask")  # mask|drop|tag

# ── Memory Decider ───────────────────────────────────────────────────
MEMORY_DECIDER_LLM_ENABLED: bool = _bool_env("MEMORY_DECIDER_LLM_ENABLED", False)

# ── RRF ──────────────────────────────────────────────────────────────
RRF_K: int = _int_env("RRF_K", 60)

# ── Observability ────────────────────────────────────────────────────
OTEL_EXPORTER_OTLP_ENDPOINT: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")
