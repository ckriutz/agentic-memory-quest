"""Embedding generator for the cold ingestion path.

Uses Azure OpenAI (or compatible provider) to generate vector embeddings.
Supports batching by count/size and retry with exponential backoff.
Caches identical content hashes to avoid redundant API calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Dict, List

from memory import config as cfg

logger = logging.getLogger(__name__)

# ── In-memory embedding cache (content_hash → vector) ────────────────
_cache: Dict[str, List[float]] = {}
_MAX_CACHE = 10_000


async def generate_embeddings(
    texts: List[str],
    *,
    max_retries: int = 3,
) -> List[List[float]]:
    """Generate embeddings for a batch of texts.

    Returns a list of embedding vectors in the same order as *texts*.
    On failure after retries, returns zero-vectors.
    """
    results: List[List[float]] = []
    to_embed: List[tuple[int, str]] = []  # (index, text)

    for i, text in enumerate(texts):
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in _cache:
            results.append(_cache[h])
        else:
            results.append([])  # placeholder
            to_embed.append((i, text))

    if not to_embed:
        return results

    # Batch call.
    batch_texts = [t for _, t in to_embed]
    vectors = await _embed_with_retry(batch_texts, max_retries=max_retries)

    for idx, (orig_i, text) in enumerate(to_embed):
        vec = vectors[idx] if idx < len(vectors) else [0.0] * cfg.AZURE_SEARCH_VECTOR_DIM
        results[orig_i] = vec
        h = hashlib.sha256(text.encode()).hexdigest()
        if len(_cache) < _MAX_CACHE:
            _cache[h] = vec

    return results


async def _embed_with_retry(
    texts: List[str], *, max_retries: int = 3
) -> List[List[float]]:
    """Call the embedding API with exponential backoff."""
    if not cfg.AZURE_OPENAI_ENDPOINT or not cfg.AZURE_OPENAI_API_KEY:
        logger.warning("Embedding credentials not configured; returning zero vectors.")
        return [[0.0] * cfg.AZURE_SEARCH_VECTOR_DIM] * len(texts)

    for attempt in range(max_retries):
        try:
            from openai import AsyncAzureOpenAI

            client = AsyncAzureOpenAI(
                api_key=cfg.AZURE_OPENAI_API_KEY,
                azure_endpoint=cfg.AZURE_OPENAI_ENDPOINT,
                api_version="2024-02-01",
            )
            response = await client.embeddings.create(
                input=texts, model=cfg.AZURE_OPENAI_EMBED_MODEL
            )
            return [item.embedding for item in response.data]
        except Exception:
            wait = 2**attempt
            logger.warning("Embedding attempt %d failed; retrying in %ds", attempt + 1, wait)
            await asyncio.sleep(wait)

    logger.error("Embedding generation failed after %d retries", max_retries)
    return [[0.0] * cfg.AZURE_SEARCH_VECTOR_DIM] * len(texts)


def clear_cache() -> None:
    """Clear the embedding cache (testing helper)."""
    _cache.clear()
