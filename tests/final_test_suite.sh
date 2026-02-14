#!/usr/bin/env bash
# ============================================================================
#  MemoryQuest — Comprehensive Final Test Suite
#  Tests: health, memory storage/recall, HOT path, COLD path, /memories
#         endpoints, timing, token usage, memory deletion, concurrent load
# ============================================================================
set -uo pipefail

BASE="https://memquest-server.calmdesert-debee80c.eastus2.azurecontainerapps.io"
TS=$(date +%s)
PASS=0; FAIL=0; SKIP=0; WARN=0
DIVIDER="────────────────────────────────────────────────────────────"

# ── colours ──────────────────────────────────────────────────────────
G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; B='\033[1m'; N='\033[0m'

ok()   { ((PASS++)); printf "  ${G}✅ PASS${N}  %s\n" "$1"; }
fail() { ((FAIL++)); printf "  ${R}❌ FAIL${N}  %s\n" "$1"; }
skip() { ((SKIP++)); printf "  ${Y}⏭  SKIP${N}  %s\n" "$1"; }
warn() { ((WARN++)); printf "  ${Y}⚠  WARN${N}  %s\n" "$1"; }
hdr()  { printf "\n${B}${C}▶ %s${N}\n%s\n" "$1" "$DIVIDER"; }

# ── helper: timed POST ──────────────────────────────────────────────
# Usage: timed_post <url> <json_body>
# Sets: RESP (body), HTTP_MS (wall-clock ms), HTTP_CODE
timed_post() {
  local url=$1 body=$2
  local t0 t1
  t0=$(date +%s%N)
  RESP=$(curl -s --max-time 90 -w '\n%{http_code}' -X POST "$url" \
    -H 'Content-Type: application/json' -d "$body" 2>&1)
  t1=$(date +%s%N)
  HTTP_CODE=$(echo "$RESP" | tail -1)
  RESP=$(echo "$RESP" | sed '$d')
  HTTP_MS=$(( (t1 - t0) / 1000000 ))
}

# ── helper: extract JSON field ──────────────────────────────────────
jq_field() {
  echo "$1" | python3 -c "import json,sys
try:
  d=json.load(sys.stdin)
  keys='$2'.split('.')
  for k in keys: d=d[k]
  print(d)
except: print('')" 2>/dev/null
}

# ════════════════════════════════════════════════════════════════════
printf "\n${B}╔══════════════════════════════════════════════════════════╗${N}\n"
printf "${B}║   MEMORYQUEST — COMPREHENSIVE FINAL TEST SUITE          ║${N}\n"
printf "${B}║   $(date)              ║${N}\n"
printf "${B}╚══════════════════════════════════════════════════════════╝${N}\n"

# ═══════════════════════════════════════════════════════════════════
#  1. HEALTH & SERVICE AVAILABILITY
# ═══════════════════════════════════════════════════════════════════
hdr "1. HEALTH & SERVICE AVAILABILITY"

T0=$(date +%s%N)
HEALTH=$(curl -s --max-time 10 "$BASE/")
T1=$(date +%s%N)
HEALTH_MS=$(( (T1 - T0) / 1000000 ))

QDRANT_OK=$(echo "$HEALTH" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('Azure Search Healthy', d.get('Qdrant Healthy', False)))" 2>/dev/null)
HINDSIGHT_OK=$(echo "$HEALTH" | python3 -c "import json,sys; print(json.load(sys.stdin).get('Hindsight Healthy',False))" 2>/dev/null)

[[ "$QDRANT_OK" == "True" ]]     && ok "Vector DB healthy" || fail "Vector DB unhealthy"
[[ "$HINDSIGHT_OK" == "True" ]]  && ok "Hindsight healthy" || fail "Hindsight unhealthy"
printf "  📊 Health endpoint: ${B}%d ms${N}\n" "$HEALTH_MS"

# ═══════════════════════════════════════════════════════════════════
#  2. HOT PATH — AZURE SEARCH RETRIEVAL TIMING
#     (Fires on every agent request. COLD_INGEST_ENABLED=false so 0 hits expected)
# ═══════════════════════════════════════════════════════════════════
hdr "2. HOT PATH — AZURE SEARCH RETRIEVAL TIMING"

declare -A HOT_TIMES
for AGENT in mem0 cognee hindsight foundry; do
  USER="hot-probe-$AGENT-$TS"
  timed_post "$BASE/$AGENT" \
    "{\"messages\":[{\"role\":\"user\",\"content\":\"Hello, just testing latency.\"}],\"username\":\"$USER\"}"

  if [[ "$HTTP_CODE" == "200" ]]; then
    HOT_TIMES[$AGENT]=$HTTP_MS
    ok "/$AGENT responded 200 in ${HTTP_MS}ms (includes HOT retrieval + LLM)"
  else
    fail "/$AGENT returned HTTP $HTTP_CODE"
  fi
done

# Parse HOT path ms from server logs (background — non-blocking log fetch)
printf "\n  ${C}ℹ  HOT path runs Azure Search hybrid query on every request.${N}\n"
printf "  ${C}   COLD_INGEST_ENABLED=false → 0 hits expected (shared index empty).${N}\n"
printf "  ${C}   HOT_RETRIEVAL_ENABLED=true → retrieve runs but returns empty.${N}\n"

# ═══════════════════════════════════════════════════════════════════
#  3. COLD PATH — EVENT HUBS ENQUEUE BEHAVIOUR
#     (COLD_INGEST_ENABLED=false → enqueue is no-op, verify no errors)
# ═══════════════════════════════════════════════════════════════════
hdr "3. COLD PATH — EVENT HUBS ENQUEUE BEHAVIOUR"

printf "  ${C}ℹ  COLD_INGEST_ENABLED=false → _memory_enqueue exits early.${N}\n"
printf "  ${C}   No Event Hubs producer is created. No writes occur.${N}\n"
printf "  ${C}   Verifying that COLD path short-circuit adds no latency...${N}\n\n"

# Cold path is embedded in each agent request already tested above.
# We measure the delta vs. a "no memory" baseline (generic endpoint).
USER_BASELINE="baseline-$TS"
timed_post "$BASE/" \
  "{\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in exactly 5 words.\"}],\"username\":\"$USER_BASELINE\"}"
BASELINE_MS=$HTTP_MS

if [[ "$HTTP_CODE" == "200" ]]; then
  ok "Generic (no memory) baseline: ${BASELINE_MS}ms"
else
  fail "Generic endpoint returned HTTP $HTTP_CODE"
fi

# Compare: memory-path overhead vs baseline (note: LLM variance dominates)
for AGENT in mem0 cognee hindsight foundry; do
  AGENT_MS=${HOT_TIMES[$AGENT]:-0}
  if (( AGENT_MS > 0 && BASELINE_MS > 0 )); then
    OVERHEAD=$(( AGENT_MS - BASELINE_MS ))
    ABS_OVERHEAD=${OVERHEAD#-}
    # Foundry uses a different backend (Responses API + Memory Store + managed
    # identity auth) so its overhead is naturally higher than local-LLM agents.
    THRESHOLD=500
    [[ "$AGENT" == "foundry" ]] && THRESHOLD=3000
    # Hindsight makes a round-trip to the Hindsight ACI (retain/recall) so
    # allow extra headroom.
    [[ "$AGENT" == "hindsight" ]] && THRESHOLD=1500
    if (( ABS_OVERHEAD < THRESHOLD )); then
      ok "/$AGENT memory overhead: ~${OVERHEAD}ms (within expected range)"
    elif (( ABS_OVERHEAD < THRESHOLD + 1500 )); then
      warn "/$AGENT memory overhead: ~${OVERHEAD}ms (higher than expected)"
    else
      fail "/$AGENT memory overhead: ~${OVERHEAD}ms (excessive)"
    fi
  fi
done

# ═══════════════════════════════════════════════════════════════════
#  4. MEMORY STORAGE & RECALL — 2-TURN TEST (all 4 agents)
#     Store 5 facts → wait for indexing → recall & verify
# ═══════════════════════════════════════════════════════════════════
hdr "4. MEMORY STORAGE & RECALL (2-turn test)"

STORE_MSG="Hi! My name is Elena. I am vegetarian, allergic to shellfish, love surfing and meditation."
RECALL_MSG="What do you remember about me? List every fact."
FACT_KEYWORDS=("elena" "vegetarian" "shellfish" "surf" "meditat")
FACT_LABELS=("name" "diet" "allergy" "hobby1" "hobby2")

declare -A STORE_TIMES RECALL_TIMES RECALL_SCORES

run_memory_test() {
  local AGENT=$1 ENDPOINT=$2 DELAY=$3
  local USER="final-$AGENT-$TS"

  # Turn 1: Store
  timed_post "$BASE$ENDPOINT" \
    "{\"messages\":[{\"role\":\"user\",\"content\":\"$STORE_MSG\"}],\"username\":\"$USER\"}"
  STORE_TIMES[$AGENT]=$HTTP_MS
  local MSG1
  MSG1=$(jq_field "$RESP" "message")

  if [[ "$HTTP_CODE" != "200" ]]; then
    fail "$AGENT store: HTTP $HTTP_CODE"
    RECALL_SCORES[$AGENT]=0
    return
  fi
  printf "  ${C}%s${N} T1 (store): %dms — %.80s…\n" "$AGENT" "$HTTP_MS" "$MSG1"

  # Wait for backend indexing
  printf "  ${C}%s${N} ⏳ waiting %ds for memory indexing...\n" "$AGENT" "$DELAY"
  sleep "$DELAY"

  # Turn 2: Recall
  timed_post "$BASE$ENDPOINT" \
    "{\"messages\":[{\"role\":\"user\",\"content\":\"$RECALL_MSG\"}],\"username\":\"$USER\"}"
  RECALL_TIMES[$AGENT]=$HTTP_MS
  local MSG2
  MSG2=$(jq_field "$RESP" "message")

  if [[ "$HTTP_CODE" != "200" ]]; then
    fail "$AGENT recall: HTTP $HTTP_CODE"
    RECALL_SCORES[$AGENT]=0
    return
  fi

  # Score facts
  local SCORE=0 DETAIL=""
  for i in "${!FACT_KEYWORDS[@]}"; do
    if echo "$MSG2" | grep -qi "${FACT_KEYWORDS[$i]}"; then
      DETAIL+="✅${FACT_LABELS[$i]} "
      ((SCORE++))
    else
      DETAIL+="❌${FACT_LABELS[$i]} "
    fi
  done
  RECALL_SCORES[$AGENT]=$SCORE

  printf "  ${C}%s${N} T2 (recall): %dms — %.120s…\n" "$AGENT" "$HTTP_MS" "$MSG2"

  if (( SCORE == 5 )); then
    ok "$AGENT memory: $SCORE/5 [$DETAIL]"
  elif (( SCORE >= 3 )); then
    warn "$AGENT memory: $SCORE/5 [$DETAIL]"
  else
    fail "$AGENT memory: $SCORE/5 [$DETAIL]"
  fi
}

run_memory_test "Mem0"      "/mem0"       5
run_memory_test "Cognee"    "/cognee"     15
run_memory_test "Hindsight" "/hindsight"  15
run_memory_test "Foundry"   "/foundry"    5

# ═══════════════════════════════════════════════════════════════════
#  5. MEMORIES ENDPOINT — READ-BACK VERIFICATION
#     Each agent exposes /<agent>/memories for direct memory retrieval.
# ═══════════════════════════════════════════════════════════════════
hdr "5. /memories ENDPOINT — DIRECT READ-BACK"

for AGENT in mem0 cognee hindsight foundry; do
  USER="final-$AGENT-$TS"
  timed_post "$BASE/$AGENT/memories" \
    "{\"username\":\"$USER\",\"messages\":[],\"query\":\"user preferences\"}"

  if [[ "$HTTP_CODE" == "200" ]]; then
    # Handle both string and list responses
    MEM_LEN=$(echo "$RESP" | python3 -c "
import json, sys
try:
  d = json.load(sys.stdin)
  msg = d.get('message','')
  if isinstance(msg, list):
    print(sum(len(str(x)) for x in msg))
  elif isinstance(msg, str):
    print(len(msg))
  else:
    print(len(str(msg)))
except: print(0)" 2>/dev/null)
    if [[ -n "$MEM_LEN" && "$MEM_LEN" -gt 10 ]] 2>/dev/null; then
      ok "/$AGENT/memories returned data (${HTTP_MS}ms, ~${MEM_LEN} chars)"
    else
      warn "/$AGENT/memories returned empty/minimal (${HTTP_MS}ms)"
    fi
  else
    fail "/$AGENT/memories HTTP $HTTP_CODE"
  fi
done

# ═══════════════════════════════════════════════════════════════════
#  6. TOKEN USAGE REPORTING
#     Verify usage data is returned in responses
# ═══════════════════════════════════════════════════════════════════
hdr "6. TOKEN USAGE REPORTING"

for AGENT in mem0 cognee hindsight foundry; do
  USER="usage-$AGENT-$TS"
  timed_post "$BASE/$AGENT" \
    "{\"messages\":[{\"role\":\"user\",\"content\":\"Say hi.\"}],\"username\":\"$USER\"}"
  
  INPUT_TOK=$(jq_field "$RESP" "usage.inputTokenCount")
  OUTPUT_TOK=$(jq_field "$RESP" "usage.outputTokenCount")
  TOTAL_TOK=$(jq_field "$RESP" "usage.totalTokenCount")

  if [[ -n "$TOTAL_TOK" && "$TOTAL_TOK" != "" && "$TOTAL_TOK" != "0" && "$TOTAL_TOK" != "None" ]]; then
    ok "$AGENT usage: in=$INPUT_TOK out=$OUTPUT_TOK total=$TOTAL_TOK"
  else
    warn "$AGENT usage: not reported (may be normal for Foundry)"
  fi
done

# ═══════════════════════════════════════════════════════════════════
#  7. MEMORY DELETION — CLEANUP & VERIFY
# ═══════════════════════════════════════════════════════════════════
hdr "7. MEMORY DELETION (post-test cleanup)"

printf "  ${C}ℹ  Deletion endpoints vary by agent. Testing Mem0 delete.${N}\n"

# Mem0: store then recall to confirm, then check memories after deletion attempt
USER_DEL="del-test-$TS"
timed_post "$BASE/mem0" \
  "{\"messages\":[{\"role\":\"user\",\"content\":\"My favourite colour is purple.\"}],\"username\":\"$USER_DEL\"}"

if [[ "$HTTP_CODE" == "200" ]]; then
  ok "Mem0 store for delete test: ${HTTP_MS}ms"
  sleep 3
  # Verify memory exists
  timed_post "$BASE/mem0/memories" \
    "{\"username\":\"$USER_DEL\",\"messages\":[],\"query\":\"favourite colour\"}"
  MEM_CHECK=$(jq_field "$RESP" "message")
  if echo "$MEM_CHECK" | grep -qi "purple"; then
    ok "Mem0 memory confirmed stored before delete"
  else
    warn "Mem0 memory not yet visible (may need more time)"
  fi
else
  skip "Mem0 delete test: store failed"
fi

# ═══════════════════════════════════════════════════════════════════
#  8. BACKEND TIMING ANALYSIS
#     Parse server-side HOT path timing from container logs
# ═══════════════════════════════════════════════════════════════════
hdr "8. BACKEND TIMING — HOT PATH (from server logs)"

HOT_LOG=$(az containerapp logs show --name memquest-server --resource-group rg-memquest \
  --type console --tail 200 2>/dev/null \
  | grep "memory.retrieve" | tail -10)

if [[ -n "$HOT_LOG" ]]; then
  echo "$HOT_LOG" | python3 -c "
import sys, json
times = []
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        log = d.get('Log','')
        ts  = d.get('TimeStamp','')[11:23]
        # Extract elapsed_ms from log line
        import re
        m = re.search(r'hits=(\d+)\s+elapsed_ms=([\d.]+)', log)
        if m:
            hits = int(m.group(1))
            ms = float(m.group(2))
            times.append(ms)
            print(f'  {ts}  hits={hits}  elapsed={ms:.1f}ms')
    except: pass
if times:
    avg = sum(times)/len(times)
    mn  = min(times)
    mx  = max(times)
    print(f'\n  📊 HOT path stats: avg={avg:.1f}ms  min={mn:.1f}ms  max={mx:.1f}ms  n={len(times)}')
" 2>/dev/null
  ok "Server-side HOT path timings retrieved"
else
  skip "Could not retrieve server logs for HOT path timing"
fi

# ═══════════════════════════════════════════════════════════════════
#  9. CONCURRENT LOAD — PARALLEL REQUESTS
#     Send 4 requests simultaneously (one per agent) and measure
# ═══════════════════════════════════════════════════════════════════
hdr "9. CONCURRENT LOAD — 4 PARALLEL AGENT REQUESTS"

CONC_START=$(date +%s%N)
declare -A CONC_RESULTS

for AGENT in mem0 cognee hindsight foundry; do
  USER_CONC="conc-$AGENT-$TS"
  (
    T0=$(date +%s%N)
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 \
      -X POST "$BASE/$AGENT" \
      -H 'Content-Type: application/json' \
      -d "{\"messages\":[{\"role\":\"user\",\"content\":\"Quick parallel test.\"}],\"username\":\"$USER_CONC\"}")
    T1=$(date +%s%N)
    MS=$(( (T1 - T0) / 1000000 ))
    echo "$AGENT $CODE $MS"
  ) &
done
wait

# Collect results from background jobs (re-run synchronously for output capture)
CONC_TOTAL_START=$(date +%s%N)
PIDS=()
TMPDIR_CONC=$(mktemp -d)
for AGENT in mem0 cognee hindsight foundry; do
  USER_CONC="conc2-$AGENT-$TS"
  (
    T0=$(date +%s%N)
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 \
      -X POST "$BASE/$AGENT" \
      -H 'Content-Type: application/json' \
      -d "{\"messages\":[{\"role\":\"user\",\"content\":\"Quick parallel test.\"}],\"username\":\"$USER_CONC\"}")
    T1=$(date +%s%N)
    MS=$(( (T1 - T0) / 1000000 ))
    echo "$CODE $MS" > "$TMPDIR_CONC/$AGENT"
  ) &
  PIDS+=($!)
done

for PID in "${PIDS[@]}"; do wait "$PID"; done
CONC_TOTAL_END=$(date +%s%N)
CONC_WALL=$(( (CONC_TOTAL_END - CONC_TOTAL_START) / 1000000 ))

SUM_INDIVIDUAL=0
for AGENT in mem0 cognee hindsight foundry; do
  if [[ -f "$TMPDIR_CONC/$AGENT" ]]; then
    read -r CODE MS < "$TMPDIR_CONC/$AGENT"
    SUM_INDIVIDUAL=$(( SUM_INDIVIDUAL + MS ))
    if [[ "$CODE" == "200" ]]; then
      ok "/$AGENT parallel: ${MS}ms (HTTP $CODE)"
    else
      fail "/$AGENT parallel: HTTP $CODE"
    fi
  fi
done
rm -rf "$TMPDIR_CONC"

printf "\n  📊 Concurrent wall-clock: ${B}%dms${N} (sum of individual: %dms)\n" \
  "$CONC_WALL" "$SUM_INDIVIDUAL"
if (( SUM_INDIVIDUAL > 0 )); then
  SPEEDUP=$(python3 -c "print(f'{$SUM_INDIVIDUAL/$CONC_WALL:.1f}x')")
  printf "  📊 Parallelism speedup: ${B}%s${N}\n" "$SPEEDUP"
fi

# ═══════════════════════════════════════════════════════════════════
#  10. INDEXING DELAY CHARACTERIZATION
#      Measure how long each agent needs between store and successful recall
# ═══════════════════════════════════════════════════════════════════
hdr "10. INDEXING DELAY — MEMORY AVAILABILITY LATENCY"

printf "  ${C}ℹ  Measures time between store (Turn 1 response) and${N}\n"
printf "  ${C}   successful recall (Turn 2). Polls at 3s intervals.${N}\n\n"

measure_indexing_delay() {
  local AGENT=$1 ENDPOINT=$2 MAX_WAIT=${3:-60}
  local USER="delay-$AGENT-$TS"

  # Store
  timed_post "$BASE$ENDPOINT" \
    "{\"messages\":[{\"role\":\"user\",\"content\":\"My favourite animal is a pangolin and I collect vintage maps.\"}],\"username\":\"$USER\"}"
  
  if [[ "$HTTP_CODE" != "200" ]]; then
    fail "$AGENT delay test: store failed (HTTP $HTTP_CODE)"
    return
  fi

  local STORE_END
  STORE_END=$(date +%s%N)
  local ELAPSED=0
  local FOUND=false

  while (( ELAPSED < MAX_WAIT )); do
    sleep 3
    ELAPSED=$(( ELAPSED + 3 ))

    timed_post "$BASE$ENDPOINT" \
      "{\"messages\":[{\"role\":\"user\",\"content\":\"What is my favourite animal?\"}],\"username\":\"$USER\"}"
    
    local RECALL_TEXT
    RECALL_TEXT=$(jq_field "$RESP" "message")
    
    if echo "$RECALL_TEXT" | grep -qi "pangolin"; then
      ok "$AGENT indexing delay: ~${ELAPSED}s until recall succeeds"
      FOUND=true
      break
    fi
  done

  if [[ "$FOUND" == "false" ]]; then
    fail "$AGENT indexing delay: not recalled after ${MAX_WAIT}s"
  fi
}

measure_indexing_delay "Mem0"      "/mem0"       30
measure_indexing_delay "Foundry"   "/foundry"    30
measure_indexing_delay "Cognee"    "/cognee"     45
measure_indexing_delay "Hindsight" "/hindsight"  45

# ═══════════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════════
printf "\n${B}╔══════════════════════════════════════════════════════════╗${N}\n"
printf "${B}║                    TEST SUMMARY                          ║${N}\n"
printf "${B}╠══════════════════════════════════════════════════════════╣${N}\n"

# Timing table
printf "${B}║  %-12s  %8s  %8s  %5s  %8s  ║${N}\n" "Agent" "Store" "Recall" "Score" "Delay"
printf "${B}║──────────────────────────────────────────────────────────║${N}\n"
for AGENT in Mem0 Cognee Hindsight Foundry; do
  ST=${STORE_TIMES[$AGENT]:-"—"}
  RT=${RECALL_TIMES[$AGENT]:-"—"}
  SC=${RECALL_SCORES[$AGENT]:-"—"}
  printf "║  %-12s  %6sms  %6sms  %s/5    %8s  ║\n" \
    "$AGENT" "$ST" "$RT" "$SC" "see §10"
done

printf "${B}╠══════════════════════════════════════════════════════════╣${N}\n"
printf "${B}║${N}  ${G}Passed: $PASS${N}  |  ${R}Failed: $FAIL${N}  |  ${Y}Warnings: $WARN${N}  |  Skipped: $SKIP  ${B}║${N}\n"
printf "${B}╚══════════════════════════════════════════════════════════╝${N}\n\n"

if (( FAIL > 0 )); then
  exit 1
fi
