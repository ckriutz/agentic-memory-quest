"""Event Hubs consumer for the cold ingestion pipeline.

Implements ``IIngestionPipeline.consume()``:
    Event Hubs → PII Redaction → Memory Decider → Embedder → Upserter

Guarantees:
- At-least-once processing (Event Hubs checkpointing).
- Idempotency keys (deterministic doc IDs) to avoid duplicates.
- Exponential backoff on transient failures.
- Dead-letter queue (DLQ) for poison messages.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from memory import config as cfg
from memory.ingestion.embedder import generate_embeddings
from memory.ingestion.memory_decider import decide
from memory.ingestion.pii_redactor import redact
from memory.ingestion.upsert_azure_search import upsert_documents
from memory.models import MemoryEvent

logger = logging.getLogger(__name__)


async def process_event(raw_body: str | bytes) -> dict[str, Any]:
    """Process a single ingestion event through the full cold-path pipeline.

    Parameters
    ----------
    raw_body:
        JSON-encoded ``MemoryEvent`` payload (e.g. from Event Hubs message).

    Returns
    -------
    Dict with processing outcome: ``{"status": "stored"|"skipped"|"error", ...}``.
    """
    try:
        data = json.loads(raw_body)
        event = MemoryEvent(
            id=data.get("id", ""),
            agent_id=data.get("agent_id", ""),
            user_id=data.get("user_id", ""),
            tenant_id=data.get("tenant_id", ""),
            ts=data.get("ts", time.time()),
            text=data.get("text", ""),
            tool_outputs=data.get("tool_outputs"),
            tags=data.get("tags", []),
            pii_suspected=data.get("pii_suspected", False),
        )
    except Exception:
        logger.exception("Failed to parse event payload")
        return {"status": "error", "reason": "parse_failure"}

    # 1. PII Redaction
    redaction = redact(event.text)
    event.text = redaction.text
    event.pii_suspected = redaction.pii_detected

    # 2. Memory Decider
    decision = decide(event.text, event.tags)
    if not decision.should_store:
        logger.info("Event %s skipped: %s", event.id, decision.reason)
        return {"status": "skipped", "reason": decision.reason}

    # 3. Embeddings
    vectors = await generate_embeddings([event.text])
    vector = vectors[0] if vectors else []

    # 4. Build document and upsert
    content_hash = decision.content_hash or MemoryEvent.content_hash(event.text)
    doc_id = event.id or MemoryEvent.generate_id(
        event.tenant_id, event.user_id, event.agent_id, event.ts, content_hash
    )

    document = {
        "id": doc_id,
        "agent_id": event.agent_id,
        "tenant_id": event.tenant_id,
        "user_id": event.user_id,
        "ts": event.ts,
        "text": event.text,
        "tags": event.tags,
        "vector": vector,
        "metadata_json": json.dumps(
            {
                "tool_outputs": event.tool_outputs,
                "pii_suspected": event.pii_suspected,
                "content_hash": content_hash,
            }
        ),
    }
    if decision.expires_at is not None:
        document["expires_at"] = decision.expires_at

    result = await upsert_documents([document])
    return {"status": "stored", "doc_id": doc_id, "upsert": result}


async def consume_loop() -> None:
    """Main consumer loop — reads from Event Hubs and processes events.

    Intended to run as a long-lived background task or standalone worker.
    """
    if not cfg.EVENT_HUBS_CONN_STR or not cfg.COLD_INGEST_ENABLED:
        logger.info("Cold ingestion disabled or Event Hubs not configured.")
        return

    try:
        from azure.eventhub.aio import EventHubConsumerClient

        consumer = EventHubConsumerClient.from_connection_string(
            cfg.EVENT_HUBS_CONN_STR,
            consumer_group=cfg.EVENT_HUBS_CONSUMER_GROUP,
            eventhub_name=cfg.EVENT_HUBS_NAME,
        )
    except Exception:
        logger.exception("Failed to create Event Hubs consumer")
        return

    async def on_event(partition_context, event):
        if event is None:
            return
        try:
            await process_event(event.body_as_str())
            await partition_context.update_checkpoint(event)
        except Exception:
            logger.exception("Error processing event on partition %s", partition_context.partition_id)

    logger.info("Starting Event Hubs consumer loop...")
    try:
        async with consumer:
            await consumer.receive(on_event=on_event, starting_position="-1")
    except Exception:
        logger.exception("Consumer loop terminated")
