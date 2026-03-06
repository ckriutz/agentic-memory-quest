#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
#  A/B COMPARISON TEST — Original (Qdrant) vs Turbo (Azure AI Search)
#
#  Runs the same test scenarios against both deployments and writes
#  a side-by-side markdown comparison to tests/results/.
# ═══════════════════════════════════════════════════════════════════

# --- Configuration ---
ORIGINAL_URL="${ORIGINAL_URL:-https://memquest-server.calmdesert-debee80c.eastus2.azurecontainerapps.io}"
TURBO_URL="${TURBO_URL:-https://memquest-server-turbo.calmdesert-debee80c.eastus2.azurecontainerapps.io}"
TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/results"
RESULT_FILE="${RESULTS_DIR}/ab_comparison_${TS}.md"

mkdir -p "$RESULTS_DIR"

# --- Formatting ---
B="\033[1m"
G="\033[32m"
R="\033[31m"
Y="\033[33m"
C="\033[36m"
N="\033[0m"

PASS=0
FAIL=0
WARN=0

ok()   { ((PASS++)); printf "  ${G}✅ PASS${N} %s\n" "$*"; }
fail() { ((FAIL++)); printf "  ${R}❌ FAIL${N} %s\n" "$*"; }
warn() { ((WARN++)); printf "  ${Y}⚠️  WARN${N} %s\n" "$*"; }
hdr()  { printf "\n${B}${C}── %s ──${N}\n" "$*"; }

# --- Helpers ---
declare -A HTTP_CODE_MAP
declare -A HTTP_MS_MAP
declare -A HTTP_BODY_MAP

timed_post() {
  local label="$1" url="$2" body="$3"
  local t0 t1 tmpfile
  tmpfile=$(mktemp)
  t0=$(date +%s%N)
  HTTP_CODE_MAP[$label]=$(curl -s -o "$tmpfile" -w "%{http_code}" --max-time 30 \
    -X POST "$url" \
    -H 'Content-Type: application/json' \
    -d "$body" 2>/dev/null || echo "000")
  t1=$(date +%s%N)
  HTTP_MS_MAP[$label]=$(( (t1 - t0) / 1000000 ))
  HTTP_BODY_MAP[$label]=$(cat "$tmpfile")
  rm -f "$tmpfile"
}

timed_get() {
  local label="$1" url="$2"
  local t0 t1 tmpfile
  tmpfile=$(mktemp)
  t0=$(date +%s%N)
  HTTP_CODE_MAP[$label]=$(curl -s -o "$tmpfile" -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  t1=$(date +%s%N)
  HTTP_MS_MAP[$label]=$(( (t1 - t0) / 1000000 ))
  HTTP_BODY_MAP[$label]=$(cat "$tmpfile")
  rm -f "$tmpfile"
}

# ═══════════════════════════════════════════════════════════════════
hdr "A/B COMPARISON TEST"
printf "  Original: ${B}%s${N}\n" "$ORIGINAL_URL"
printf "  Turbo:    ${B}%s${N}\n" "$TURBO_URL"
printf "  Output:   ${B}%s${N}\n\n" "$RESULT_FILE"

# Start building the output file
cat > "$RESULT_FILE" <<EOF
# A/B Comparison: Original vs Turbo

**Date:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')
**Original:** $ORIGINAL_URL
**Turbo:** $TURBO_URL

---

## 1. Health Check

| Metric | Original | Turbo |
|--------|----------|-------|
EOF

# ═══════════════════════════════════════════════════════════════════
#  1. HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════
hdr "1. HEALTH CHECK"

timed_get "orig_health" "$ORIGINAL_URL/"
timed_get "turbo_health" "$TURBO_URL/"

printf "  Original: HTTP %s in %dms\n" "${HTTP_CODE_MAP[orig_health]}" "${HTTP_MS_MAP[orig_health]}"
printf "  Turbo:    HTTP %s in %dms\n" "${HTTP_CODE_MAP[turbo_health]}" "${HTTP_MS_MAP[turbo_health]}"

[[ "${HTTP_CODE_MAP[orig_health]}" == "200" ]] && ok "Original healthy" || fail "Original unhealthy"
[[ "${HTTP_CODE_MAP[turbo_health]}" == "200" ]] && ok "Turbo healthy" || fail "Turbo unhealthy"

cat >> "$RESULT_FILE" <<EOF
| HTTP Status | ${HTTP_CODE_MAP[orig_health]} | ${HTTP_CODE_MAP[turbo_health]} |
| Response Time | ${HTTP_MS_MAP[orig_health]}ms | ${HTTP_MS_MAP[turbo_health]}ms |
| Response | $(echo "${HTTP_BODY_MAP[orig_health]}" | head -c 200) | $(echo "${HTTP_BODY_MAP[turbo_health]}" | head -c 200) |

---

## 2. Agent Response Times

| Agent | Original (ms) | Turbo (ms) | Δ (ms) | Faster |
|-------|---------------|------------|--------|--------|
EOF

# ═══════════════════════════════════════════════════════════════════
#  2. AGENT RESPONSE TIMES
# ═══════════════════════════════════════════════════════════════════
hdr "2. AGENT RESPONSE TIMES"

TEST_USER="ab-test-${TS}"

for AGENT in mem0 cognee hindsight foundry; do
  BODY="{\"messages\":[{\"role\":\"user\",\"content\":\"Hello, what amenities does the resort have?\"}],\"username\":\"${TEST_USER}-${AGENT}\"}"
  
  timed_post "orig_${AGENT}" "$ORIGINAL_URL/$AGENT" "$BODY"
  timed_post "turbo_${AGENT}" "$TURBO_URL/$AGENT" "$BODY"

  ORIG_MS=${HTTP_MS_MAP[orig_${AGENT}]}
  TURBO_MS=${HTTP_MS_MAP[turbo_${AGENT}]}
  ORIG_CODE=${HTTP_CODE_MAP[orig_${AGENT}]}
  TURBO_CODE=${HTTP_CODE_MAP[turbo_${AGENT}]}

  DELTA=$(( TURBO_MS - ORIG_MS ))
  if [[ $DELTA -lt 0 ]]; then
    FASTER="⚡ Turbo"
  elif [[ $DELTA -gt 0 ]]; then
    FASTER="Original"
  else
    FASTER="Tie"
  fi

  printf "  %-10s  Original: %4dms (HTTP %s)  |  Turbo: %4dms (HTTP %s)  |  Δ: %+dms (%s)\n" \
    "$AGENT" "$ORIG_MS" "$ORIG_CODE" "$TURBO_MS" "$TURBO_CODE" "$DELTA" "$FASTER"

  [[ "$ORIG_CODE" == "200" ]] && ok "Original /$AGENT responded 200" || fail "Original /$AGENT returned $ORIG_CODE"
  [[ "$TURBO_CODE" == "200" ]] && ok "Turbo /$AGENT responded 200" || fail "Turbo /$AGENT returned $TURBO_CODE"

  echo "| $AGENT | $ORIG_MS | $TURBO_MS | ${DELTA} | $FASTER |" >> "$RESULT_FILE"
done

# ═══════════════════════════════════════════════════════════════════
#  3. MEMORY STORE + RECALL
# ═══════════════════════════════════════════════════════════════════
hdr "3. MEMORY STORE + RECALL"

cat >> "$RESULT_FILE" <<EOF

---

## 3. Memory Store + Recall

| Agent | Version | Store | Recall | Memory Found |
|-------|---------|-------|--------|--------------|
EOF

RECALL_USER="ab-recall-${TS}"

for AGENT in mem0 cognee; do
  for VERSION in orig turbo; do
    if [[ "$VERSION" == "orig" ]]; then
      BASE="$ORIGINAL_URL"
      LABEL="Original"
    else
      BASE="$TURBO_URL"
      LABEL="Turbo"
    fi

    USER="${RECALL_USER}-${VERSION}-${AGENT}"

    # Store a fact
    STORE_BODY="{\"messages\":[{\"role\":\"user\",\"content\":\"My name is TestUser and I love chocolate cake.\"}],\"username\":\"${USER}\"}"
    timed_post "${VERSION}_${AGENT}_store" "$BASE/$AGENT" "$STORE_BODY"
    STORE_CODE=${HTTP_CODE_MAP[${VERSION}_${AGENT}_store]}
    STORE_MS=${HTTP_MS_MAP[${VERSION}_${AGENT}_store]}

    # Wait for background save
    sleep 3

    # Recall
    RECALL_BODY="{\"messages\":[{\"role\":\"user\",\"content\":\"What do you know about me?\"}],\"username\":\"${USER}\"}"
    timed_post "${VERSION}_${AGENT}_recall" "$BASE/$AGENT" "$RECALL_BODY"
    RECALL_CODE=${HTTP_CODE_MAP[${VERSION}_${AGENT}_recall]}
    RECALL_MS=${HTTP_MS_MAP[${VERSION}_${AGENT}_recall]}
    RECALL_BODY_TEXT=${HTTP_BODY_MAP[${VERSION}_${AGENT}_recall]}

    # Check if the recall mentions chocolate
    HAS_MEMORY="❌"
    if echo "$RECALL_BODY_TEXT" | grep -qi "chocolate"; then
      HAS_MEMORY="✅"
    fi

    printf "  %-6s %-8s  Store: %dms (HTTP %s)  Recall: %dms (HTTP %s)  Memory: %s\n" \
      "$AGENT" "$LABEL" "$STORE_MS" "$STORE_CODE" "$RECALL_MS" "$RECALL_CODE" "$HAS_MEMORY"

    [[ "$STORE_CODE" == "200" ]] && ok "$LABEL /$AGENT store" || fail "$LABEL /$AGENT store ($STORE_CODE)"
    [[ "$RECALL_CODE" == "200" ]] && ok "$LABEL /$AGENT recall" || fail "$LABEL /$AGENT recall ($RECALL_CODE)"

    echo "| $AGENT | $LABEL | ${STORE_MS}ms (${STORE_CODE}) | ${RECALL_MS}ms (${RECALL_CODE}) | $HAS_MEMORY |" >> "$RESULT_FILE"
  done
done

# ═══════════════════════════════════════════════════════════════════
#  4. DELETE MEMORIES
# ═══════════════════════════════════════════════════════════════════
hdr "4. CLEANUP — DELETE TEST MEMORIES"

cat >> "$RESULT_FILE" <<EOF

---

## 4. Cleanup

| Agent | Version | Delete Status |
|-------|---------|---------------|
EOF

for AGENT in mem0 cognee; do
  for VERSION in orig turbo; do
    if [[ "$VERSION" == "orig" ]]; then
      BASE="$ORIGINAL_URL"
      LABEL="Original"
    else
      BASE="$TURBO_URL"
      LABEL="Turbo"
    fi

    USER="${RECALL_USER}-${VERSION}-${AGENT}"
    DEL_BODY="{\"username\":\"${USER}\",\"messages\":[]}"
    timed_post "${VERSION}_${AGENT}_del" "$BASE/$AGENT/delete" "$DEL_BODY"
    DEL_CODE=${HTTP_CODE_MAP[${VERSION}_${AGENT}_del]}

    if [[ "$DEL_CODE" == "200" ]] || [[ "$DEL_CODE" == "404" ]]; then
      ok "$LABEL /$AGENT/delete (HTTP $DEL_CODE)"
      echo "| $AGENT | $LABEL | ✅ (HTTP $DEL_CODE) |" >> "$RESULT_FILE"
    else
      warn "$LABEL /$AGENT/delete returned $DEL_CODE"
      echo "| $AGENT | $LABEL | ⚠️ (HTTP $DEL_CODE) |" >> "$RESULT_FILE"
    fi
  done
done

# ═══════════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════════
hdr "SUMMARY"

TOTAL=$((PASS + FAIL + WARN))
printf "\n  ${G}PASS: %d${N}  ${R}FAIL: %d${N}  ${Y}WARN: %d${N}  TOTAL: %d\n\n" "$PASS" "$FAIL" "$WARN" "$TOTAL"

cat >> "$RESULT_FILE" <<EOF

---

## Summary

| Metric | Count |
|--------|-------|
| ✅ PASS | $PASS |
| ❌ FAIL | $FAIL |
| ⚠️ WARN | $WARN |
| **Total** | **$TOTAL** |

---

*Generated by compare_ab.sh on $(date -u '+%Y-%m-%d %H:%M:%S UTC')*
EOF

printf "  📄 Results written to: ${B}%s${N}\n\n" "$RESULT_FILE"

# Exit with failure if any test failed
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
