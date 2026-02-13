# Memory Architecture — HOT/COLD Design

> **Status:** Active  
> **Version:** 1.0  
> **Last Updated:** 2026-02-13

## Overview

The agentic-memory-quest server now includes a **shared, configurable memory layer** with two independent paths:

| Path | Direction | Latency | Blocking? |
|------|-----------|---------|-----------|
| **HOT** | Read-only retrieval | Sub-100 ms target | Synchronous during request |
| **COLD** | Async ingestion | Best-effort | Non-blocking (fire-and-forget) |

The memory layer is integrated into **all agents** (`agent-framework`, `mem0`, `cognee`, `hindsight`, `foundry`) **except** the `none` generic endpoint.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
                 ┌─────────────────┐
                 │   FastAPI Server │
                 │   (server.py)   │
                 └────┬───────┬────┘
                      │       │
         ┌────────────┘       └─────────────┐
         ▼                                  ▼
 ┌───────────────┐                 ┌────────────────┐
 │   HOT PATH    │                 │   COLD PATH    │
 │  (retrieve)   │                 │ (enqueue_write) │
 │  Read-only    │                 │  Fire-and-forget│
 └───────┬───────┘                 └───────┬────────┘
         │                                 │
         ▼                                 ▼
 ┌───────────────────┐            ┌────────────────────┐
 │  Query Embedding   │            │    Event Hubs      │
 │  (Azure OpenAI)    │            │   (Partitioned by  │
 └───────┬───────────┘            │    tenant/user)    │
         │                        └───────┬────────────┘
         ▼                                │
 ┌───────────────────┐                    ▼
 │  Hybrid Retrieval  │           ┌────────────────────┐
 │  ┌─────┐ ┌──────┐ │           │  PII Redactor       │
 │  │BM25 │ │Vector│ │           │  (regex rules)      │
 │  └──┬──┘ └──┬───┘ │           └───────┬────────────┘
 │     └──┬────┘     │                   │
 │        ▼          │                   ▼
 │   RRF Fusion      │           ┌────────────────────┐
 │   (k=60)          │           │  Memory Decider     │
 └───────┬───────────┘           │  (heuristics/LLM)   │
         │                       └───────┬────────────┘
         ▼                               │
 ┌───────────────────┐                   ▼
 │ Semantic Ranker    │           ┌────────────────────┐
 │ (optional re-rank) │           │  Embedder           │
 └───────┬───────────┘           │  (Azure OpenAI)     │
         │                       └───────┬────────────┘
         ▼                               │
 ┌───────────────────┐                   ▼
 │  Top-K MemoryHits  │           ┌────────────────────┐
 │  → Prompt Assembly │           │  Upsert to Azure   │
 └────────────────────┘           │  AI Search          │
                                  │  (idempotent)       │
                                  └────────────────────┘
```

---

## HOT Path (Reads)

### Flow

1. **Compute query embedding** using Azure OpenAI (`text-embedding-3-large` by default).
2. **Sparse search**: BM25 text retrieval against Azure AI Search.
3. **Dense search**: Vector similarity (cosine via HNSW) on the same index.
4. **RRF Fusion**: Combine the two ranked lists using Reciprocal Rank Fusion (`score = Σ 1/(k + rank_i)`, default `k=60`).
5. **Semantic Ranker** (optional): If `AZURE_SEARCH_SEMANTIC_RANKER_ENABLED=true`, pass fused results to the Azure AI Search Semantic Ranker for final ordering.
6. Return top-K (`MEMORY_K`, default 8) `MemoryHit` objects.

### Constraints

- **No writes** — the hot path is strictly read-only.
- **Sub-100 ms** retrieval budget target.
- **Fallback on failure** — returns empty context (never fails the request).
- **Feature flags**: `MEMORY_ENABLED`, `HOT_RETRIEVAL_ENABLED`.

### Multi-tenant Isolation

All queries include OData filters: `tenant_id eq '...' and user_id eq '...'` ensuring strict data isolation.

---

## COLD Path (Writes)

### Pipeline Stages

```
Agent → enqueue_write(MemoryEvent) → Event Hubs
         ↓
  ┌──────────────┐
  │ PII Redactor  │ → mask/drop/tag PII patterns (emails, phones, SSNs, etc.)
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Memory Decider│ → drop low-signal chit-chat; keep preferences, facts, decisions
  └──────┬───────┘    dedup via content hash; TTL for volatile items
         ▼
  ┌──────────────┐
  │   Embedder    │ → generate vector embeddings (batched, cached, retry with backoff)
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │   Upserter    │ → idempotent merge_or_upload to Azure AI Search
  └──────────────┘    DLQ for permanently failed docs
```

### Guarantees

- **At-least-once** processing (Event Hubs checkpointing).
- **Idempotency** via deterministic document IDs: `sha256(tenant_id|user_id|agent_id|ts|content_hash)`.
- **Exponential backoff** on transient failures.
- **Dead Letter Queue** for poison messages.

### PII Redaction

| Mode | Behavior |
|------|----------|
| `mask` | Replace PII with `[REDACTED:TYPE]` |
| `drop` | Remove PII entirely |
| `tag` | Leave text intact, flag `pii_detected=true` |

Default patterns: emails, phone numbers, SSN-like, credit card numbers, IP addresses.

---

## Azure AI Search Index Schema

**Index name**: `${APP_NAME}-${ENV}-memory` (configurable via `MEMORY_INDEX_NAME`)

| Field | Type | Properties |
|-------|------|-----------|
| `id` | `Edm.String` | Key, filterable |
| `agent_id` | `Edm.String` | Filterable |
| `tenant_id` | `Edm.String` | Filterable |
| `user_id` | `Edm.String` | Filterable |
| `ts` | `Edm.DateTimeOffset` | Sortable, filterable |
| `text` | `Edm.String` | Searchable |
| `tags` | `Collection(Edm.String)` | Filterable |
| `vector` | `Collection(Edm.Single)` | Searchable (HNSW, 1536 dims) |
| `metadata_json` | `Edm.String` | Retrievable |
| `expires_at` | `Edm.DateTimeOffset` | Filterable (TTL) |

---

## Agent Integration

All agents **except `none`** have memory integration:

| Agent | HOT (retrieve) | COLD (enqueue) |
|-------|----------------|----------------|
| `agent-framework` | ✅ | ✅ |
| `mem0` | ✅ | ✅ |
| `cognee` | ✅ | ✅ |
| `hindsight` | ✅ | ✅ |
| `foundry` | ✅ | ✅ |
| `none` (generic) | ❌ | ❌ |

### Integration Pattern

```python
# HOT path: retrieve shared memory for prompt injection
mem_context = await _memory_retrieve(username, agent_id, user_query)
if mem_context:
    messages.insert(1, ChatMessage(role="system", text=mem_context))

# ... agent processes request ...

# COLD path: fire-and-forget enqueue
await _memory_enqueue(username, agent_id, user_query)
```

---

## Configuration

All feature flags and settings are controlled via environment variables. See `.env.sample` for the full list.

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_ENABLED` | `true` | Master switch for the entire memory layer |
| `HOT_RETRIEVAL_ENABLED` | `true` | Enable/disable HOT path retrieval |
| `COLD_INGEST_ENABLED` | `true` | Enable/disable COLD path ingestion |
| `AZURE_SEARCH_SEMANTIC_RANKER_ENABLED` | `false` | Toggle Semantic Ranker re-ranking |
| `PII_REDACTION_ENABLED` | `true` | Toggle PII redaction |
| `MEMORY_DECIDER_LLM_ENABLED` | `false` | Toggle LLM-assisted memory classification |

---

## Quickstart

### 1. Create the index

```bash
cd scripts/memory
python create_index.py
```

### 2. Set environment variables

Copy `.env.sample` and fill in your Azure AI Search and Event Hubs credentials.

### 3. Run tests

```bash
python -m pytest tests/memory/ -v
```

### 4. Start the server

```bash
cd server/memoryquest_server
fastapi run server.py
```

---

## Observability

- **OpenTelemetry**: Traces for `retrieve`, `enqueue_write`, and each cold-path stage.
- **Metrics**: Hot path (latency, hit-rate, timeouts) and cold path (throughput, success/failure, DLQ depth).
- **Structured logs**: Include `trace_id`, `tenant_id`, `agent_id`, `event_id` for correlation.

Configure via `OTEL_EXPORTER_OTLP_ENDPOINT`.

### Example Log Query (Azure Monitor / Grafana)

```kusto
traces
| where customDimensions.tenant_id == "my-tenant"
| where message contains "memory.retrieve"
| summarize p50=percentile(duration, 50), p95=percentile(duration, 95) by bin(timestamp, 5m)
```

---

## Security & Compliance

- PII redaction enabled by default (`mask` mode).
- Multi-tenant isolation via `tenant_id` filters on all queries.
- TLS in transit (Azure default); encryption at rest (Azure default).
- No secrets stored in memory documents.
- `authorization`-like fields are dropped before indexing.

---

## Migration & Rollback

### Creating the index
```bash
python scripts/memory/create_index.py
```

### Backfilling historical events
```bash
cat historical_events.jsonl | python scripts/memory/backfill.py
# Dry run:
cat historical_events.jsonl | python scripts/memory/backfill.py --dry-run
```

### Rollback

1. **Disable via feature flags**: Set `MEMORY_ENABLED=false` (or individually `HOT_RETRIEVAL_ENABLED=false` / `COLD_INGEST_ENABLED=false`).
2. **Stop cold ingestion**: Drop the Event Hubs consumer. The hot path continues to work read-only.
3. **Full revert** (non-prod): Delete the index using the Azure portal or SDK.

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Azure AI Search latency spike | Circuit breaker + fallback to empty context |
| Event Hubs unavailable | Events dropped silently; request continues |
| Embedding API rate limit | Exponential backoff + caching by content hash |
| PII leakage | Redaction on by default; opt-out only in non-prod |
| Index corruption | Idempotent upserts; backfill script for rebuild |
