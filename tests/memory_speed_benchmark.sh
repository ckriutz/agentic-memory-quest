#!/usr/bin/env bash
set -euo pipefail

# Memory Speed Benchmark
# Compares response times across three memory modes:
#   1. none       — No memory (generic agent)
#   2. standard   — Agent's built-in memory only
#   3. hot-cold   — Agent memory + HOT/COLD shared memory layer
#
# Usage:
#   ./tests/memory_speed_benchmark.sh [SERVER_URL] [FRAMEWORK] [NUM_ROUNDS]
#
# Examples:
#   ./tests/memory_speed_benchmark.sh http://localhost:8000 mem0 5
#   ./tests/memory_speed_benchmark.sh https://memquest-server-turbo.example.com agent-framework 3

SERVER_URL="${1:-http://localhost:8000}"
FRAMEWORK="${2:-mem0}"
NUM_ROUNDS="${3:-5}"
USERNAME="benchmark-$(date +%s)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_FILE="${RESULTS_DIR}/speed_benchmark_${TIMESTAMP}.md"

say() { printf "%s\n" "$*"; }
sep() { printf '%*s\n' 60 '' | tr ' ' '-'; }

# Test queries — a mix simulating real usage
QUERIES=(
  "Hi, my name is Alex and I love hiking."
  "What spa treatments do you recommend?"
  "I prefer evening appointments, around 7pm."
  "Can you remind me what activities I liked?"
  "I'm allergic to lavender, please note that."
)

# If fewer rounds than queries, truncate; if more, cycle
get_query() {
  local idx=$1
  local len=${#QUERIES[@]}
  echo "${QUERIES[$((idx % len))]}"
}

# Send a chat message and capture timing
# Returns: total_ms,llm_ms,mem_retrieve_ms,mem_enqueue_ms,http_ms
send_chat() {
  local endpoint="$1"
  local memory_mode="$2"
  local query="$3"
  local msg_history="$4"

  local start_ns
  start_ns=$(date +%s%N)

  local response
  response=$(curl -sS -w "\n%{http_code}" -X POST "$endpoint" \
    -H "Content-Type: application/json" \
    -d "{
      \"username\": \"${USERNAME}\",
      \"messages\": ${msg_history},
      \"memory_mode\": \"${memory_mode}\"
    }" 2>/dev/null) || { echo "ERROR,0,0,0,0"; return; }

  local end_ns
  end_ns=$(date +%s%N)
  local http_ms=$(( (end_ns - start_ns) / 1000000 ))

  local http_code
  http_code=$(echo "$response" | tail -1)
  local body
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" != "200" ]]; then
    echo "ERROR,0,0,0,${http_ms}"
    return
  fi

  # Extract timing_ms fields from JSON response
  local total_ms llm_ms mem_retrieve_ms mem_enqueue_ms
  total_ms=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timing_ms',{}).get('total',0))" 2>/dev/null || echo "0")
  llm_ms=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timing_ms',{}).get('llm',0))" 2>/dev/null || echo "0")
  mem_retrieve_ms=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timing_ms',{}).get('memory_retrieve',0))" 2>/dev/null || echo "0")
  mem_enqueue_ms=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timing_ms',{}).get('memory_enqueue',0))" 2>/dev/null || echo "0")

  echo "${total_ms},${llm_ms},${mem_retrieve_ms},${mem_enqueue_ms},${http_ms}"
}

# Run benchmark for a given mode
# Sets: result arrays for later reporting
run_benchmark() {
  local mode="$1"
  local label="$2"
  local endpoint

  if [[ "$mode" == "none" ]]; then
    endpoint="${SERVER_URL}/"
  else
    endpoint="${SERVER_URL}/${FRAMEWORK}"
  fi

  say ""
  say "=== Benchmarking: ${label} (mode=${mode}, endpoint=${endpoint}) ==="
  say ""

  local totals=()
  local llms=()
  local retrieves=()
  local enqueues=()
  local https=()
  local msg_history="[]"
  local errors=0

  for ((i=0; i<NUM_ROUNDS; i++)); do
    local query
    query=$(get_query "$i")
    say "  Round $((i+1))/${NUM_ROUNDS}: \"${query:0:50}...\""

    local result
    result=$(send_chat "$endpoint" "$mode" "$query" "$msg_history")

    IFS=',' read -r total llm retrieve enqueue http_t <<< "$result"

    if [[ "$total" == "ERROR" ]]; then
      say "    ERROR (HTTP time: ${http_t}ms)"
      ((errors++)) || true
      continue
    fi

    say "    total=${total}ms  llm=${llm}ms  retrieve=${retrieve}ms  enqueue=${enqueue}ms  http=${http_t}ms"

    totals+=("$total")
    llms+=("$llm")
    retrieves+=("$retrieve")
    enqueues+=("$enqueue")
    https+=("$http_t")

    # Build up message history for next round
    msg_history=$(python3 -c "
import json, sys
history = json.loads('''${msg_history}''')
history.append({'role': 'user', 'content': '''${query}'''})
history.append({'role': 'assistant', 'content': 'OK'})
print(json.dumps(history))
" 2>/dev/null || echo "$msg_history")

    # Small delay between requests
    sleep 1
  done

  # Compute averages
  local count=${#totals[@]}
  if [[ $count -eq 0 ]]; then
    say "  All rounds failed!"
    eval "${label}_avg_total=0"
    eval "${label}_avg_llm=0"
    eval "${label}_avg_retrieve=0"
    eval "${label}_avg_enqueue=0"
    eval "${label}_avg_http=0"
    eval "${label}_errors=${errors}"
    eval "${label}_count=0"
    return
  fi

  local sum_total=0 sum_llm=0 sum_retrieve=0 sum_enqueue=0 sum_http=0
  for ((j=0; j<count; j++)); do
    sum_total=$((sum_total + ${totals[$j]}))
    sum_llm=$((sum_llm + ${llms[$j]}))
    sum_retrieve=$((sum_retrieve + ${retrieves[$j]}))
    sum_enqueue=$((sum_enqueue + ${enqueues[$j]}))
    sum_http=$((sum_http + ${https[$j]}))
  done

  eval "${label}_avg_total=$((sum_total / count))"
  eval "${label}_avg_llm=$((sum_llm / count))"
  eval "${label}_avg_retrieve=$((sum_retrieve / count))"
  eval "${label}_avg_enqueue=$((sum_enqueue / count))"
  eval "${label}_avg_http=$((sum_http / count))"
  eval "${label}_errors=${errors}"
  eval "${label}_count=${count}"

  say ""
  say "  Summary: avg_total=$((sum_total / count))ms  avg_llm=$((sum_llm / count))ms  avg_retrieve=$((sum_retrieve / count))ms  avg_enqueue=$((sum_enqueue / count))ms"
}

# ── MAIN ──────────────────────────────────────────────────────────────

say "Memory Speed Benchmark"
say "Server:    ${SERVER_URL}"
say "Framework: ${FRAMEWORK}"
say "Rounds:    ${NUM_ROUNDS}"
say "User:      ${USERNAME}"
sep

# Run all three benchmarks
run_benchmark "none" "NO_MEMORY"
run_benchmark "standard" "STANDARD"
run_benchmark "hot-cold" "HOT_COLD"

# ── Generate Report ──────────────────────────────────────────────────

cat > "$REPORT_FILE" << EOF
# Memory Speed Benchmark Report

**Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Server:** ${SERVER_URL}
**Framework:** ${FRAMEWORK}
**Rounds per mode:** ${NUM_ROUNDS}
**Test User:** ${USERNAME}

## Results Summary

| Metric | No Memory | Standard | Hot/Cold | HC Overhead |
|--------|-----------|----------|----------|-------------|
| Avg Total (ms) | ${NO_MEMORY_avg_total} | ${STANDARD_avg_total} | ${HOT_COLD_avg_total} | $((HOT_COLD_avg_total - STANDARD_avg_total))ms |
| Avg LLM (ms) | ${NO_MEMORY_avg_llm} | ${STANDARD_avg_llm} | ${HOT_COLD_avg_llm} | $((HOT_COLD_avg_llm - STANDARD_avg_llm))ms |
| Avg Mem Retrieve (ms) | ${NO_MEMORY_avg_retrieve} | ${STANDARD_avg_retrieve} | ${HOT_COLD_avg_retrieve} | ${HOT_COLD_avg_retrieve}ms |
| Avg Mem Enqueue (ms) | ${NO_MEMORY_avg_enqueue} | ${STANDARD_avg_enqueue} | ${HOT_COLD_avg_enqueue} | ${HOT_COLD_avg_enqueue}ms |
| Avg HTTP RTT (ms) | ${NO_MEMORY_avg_http} | ${STANDARD_avg_http} | ${HOT_COLD_avg_http} | $((HOT_COLD_avg_http - STANDARD_avg_http))ms |
| Success / Total | ${NO_MEMORY_count}/${NUM_ROUNDS} | ${STANDARD_count}/${NUM_ROUNDS} | ${HOT_COLD_count}/${NUM_ROUNDS} | — |

## Analysis

### Memory Overhead
- **HOT path (retrieve) adds:** ${HOT_COLD_avg_retrieve}ms average
- **COLD path (enqueue) adds:** ${HOT_COLD_avg_enqueue}ms average
- **Total Hot/Cold overhead vs Standard:** $((HOT_COLD_avg_total - STANDARD_avg_total))ms ($( [[ ${STANDARD_avg_total} -gt 0 ]] && echo "$(( (HOT_COLD_avg_total - STANDARD_avg_total) * 100 / STANDARD_avg_total ))%" || echo "N/A" ))

### Standard Memory vs No Memory
- **Standard memory overhead:** $((STANDARD_avg_total - NO_MEMORY_avg_total))ms ($( [[ ${NO_MEMORY_avg_total} -gt 0 ]] && echo "$(( (STANDARD_avg_total - NO_MEMORY_avg_total) * 100 / NO_MEMORY_avg_total ))%" || echo "N/A" ))

## Configuration
- MEMORY_ENABLED: \`${MEMORY_ENABLED:-not set}\`
- HOT_RETRIEVAL_ENABLED: \`${HOT_RETRIEVAL_ENABLED:-not set}\`
- COLD_INGEST_ENABLED: \`${COLD_INGEST_ENABLED:-not set}\`
- MEMORY_K: \`${MEMORY_K:-not set}\`

---
*Generated by memory_speed_benchmark.sh*
EOF

say ""
sep
say "Report saved to: ${REPORT_FILE}"
say ""
cat "$REPORT_FILE"
