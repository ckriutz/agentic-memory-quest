"""Observability setup for the memory layer.

Provides OpenTelemetry tracing and structured logging with correlation IDs.
Metrics are exposed for both HOT and COLD paths.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from memory import config as cfg

logger = logging.getLogger(__name__)

# ── Metrics counters (simple in-process; replace with OTel SDK) ──────

_metrics: dict[str, float] = {
    "hot_retrieval_count": 0,
    "hot_retrieval_latency_ms_total": 0,
    "hot_retrieval_timeout_count": 0,
    "hot_retrieval_fallback_count": 0,
    "cold_ingest_count": 0,
    "cold_ingest_success": 0,
    "cold_ingest_failure": 0,
    "cold_embed_latency_ms_total": 0,
    "cold_upsert_latency_ms_total": 0,
    "cold_dlq_depth": 0,
}


def record_metric(name: str, value: float = 1.0) -> None:
    """Increment / accumulate a named metric."""
    _metrics[name] = _metrics.get(name, 0) + value


def get_metrics() -> dict[str, float]:
    """Return a snapshot of current metrics."""
    return dict(_metrics)


def reset_metrics() -> None:
    """Reset all metric counters (testing helper)."""
    for key in _metrics:
        _metrics[key] = 0


# ── Structured logging helper ────────────────────────────────────────

def log_with_context(
    level: int,
    message: str,
    *,
    trace_id: str = "",
    tenant_id: str = "",
    agent_id: str = "",
    event_id: str = "",
    **extra: Any,
) -> None:
    """Emit a structured log line with correlation IDs."""
    fields = {
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "event_id": event_id,
        **extra,
    }
    logger.log(level, "%s | %s", message, fields)


# ── Optional OpenTelemetry bootstrap ─────────────────────────────────

def init_otel() -> None:
    """Initialise OpenTelemetry tracing if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set."""
    endpoint = cfg.OTEL_EXPORTER_OTLP_ENDPOINT
    if not endpoint:
        logger.info("OTEL endpoint not configured; tracing disabled.")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": "memquest-memory"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing initialised (endpoint=%s)", endpoint)
    except ImportError:
        logger.warning("OpenTelemetry SDK not installed; tracing disabled.")
    except Exception:
        logger.exception("OpenTelemetry initialisation failed")
