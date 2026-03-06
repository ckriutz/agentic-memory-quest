#!/usr/bin/env bash
set -uo pipefail

# ═══════════════════════════════════════════════════════════════════
#  THREE-MODE COMPARISON TEST
#  Sends store + recall prompts through /compare (None vs Hot/Cold vs Standard)
#  and writes a markdown results file to tests/results/.
# ═══════════════════════════════════════════════════════════════════

SERVER_URL="${SERVER_URL:-https://memquest-server-turbo.calmdesert-debee80c.eastus2.azurecontainerapps.io}"
AGENT="${AGENT:-agent-framework}"
TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/results"
RESULT_FILE="${RESULTS_DIR}/mode_comparison_${TS}.md"
USERNAME="mode-test-${TS}"

mkdir -p "$RESULTS_DIR"

# --- Formatting ---
B="\033[1m"; G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"; N="\033[0m"
PASS=0; FAIL=0; WARN=0

ok()   { ((PASS++)); printf "  ${G}✅ PASS${N} %s\n" "$*"; }
fail() { ((FAIL++)); printf "  ${R}❌ FAIL${N} %s\n" "$*"; }
warn() { ((WARN++)); printf "  ${Y}⚠️  WARN${N} %s\n" "$*"; }
hdr()  { printf "\n${B}${C}── %s ──${N}\n" "$*"; }

# --- Helper: call /compare and parse response ---
call_compare() {
  local prompt="$1"
  local tmpfile
  tmpfile=$(mktemp)

  local http_code
  http_code=$(curl -s -o "$tmpfile" -w "%{http_code}" --max-time 120 \
    -X POST "${SERVER_URL}/compare" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "
import json, sys
print(json.dumps({
    'username': '$USERNAME',
    'messages': [{'role': 'user', 'content': $(python3 -c "import json; print(json.dumps('$prompt'))")}],
    'query': '$AGENT',
    'memory_mode': 'standard'
}))" 2>/dev/null)" 2>/dev/null || echo "000")

  if [[ "$http_code" == "200" ]]; then
    cat "$tmpfile"
  else
    echo "{\"error\": \"HTTP $http_code\"}"
  fi
  rm -f "$tmpfile"
}

# Safer helper that reads prompt from stdin to avoid shell escaping issues
call_compare_stdin() {
  local tmpfile tmpbody
  tmpfile=$(mktemp)
  tmpbody=$(mktemp)

  # Read prompt from stdin, build JSON body with python
  python3 -c "
import json, sys
prompt = sys.stdin.read().strip()
body = {
    'username': '$USERNAME',
    'messages': [{'role': 'user', 'content': prompt}],
    'query': '$AGENT',
    'memory_mode': 'standard'
}
print(json.dumps(body))
" > "$tmpbody"

  local http_code
  http_code=$(curl -s -o "$tmpfile" -w "%{http_code}" --max-time 120 \
    -X POST "${SERVER_URL}/compare" \
    -H 'Content-Type: application/json' \
    -d @"$tmpbody" 2>/dev/null || echo "000")

  if [[ "$http_code" == "200" ]]; then
    cat "$tmpfile"
  else
    echo "{\"error\": \"HTTP $http_code\"}"
  fi
  rm -f "$tmpfile" "$tmpbody"
}

# --- Extract timing fields from a mode's JSON ---
parse_timing() {
  local json="$1" mode="$2"
  python3 -c "
import json, sys
d = json.loads('''$json''')
m = d.get('$mode', {})
t = m.get('timing_ms', {})
print(f\"{t.get('memory_retrieve',0)}|{t.get('llm',0)}|{t.get('memory_enqueue',0)}|{t.get('total',0)}\")
" 2>/dev/null || echo "0|0|0|0"
}

# ═══════════════════════════════════════════════════════════════════
printf "\n${B}╔══════════════════════════════════════════════════════════════╗${N}\n"
printf "${B}║  THREE-MODE COMPARISON TEST (None / Hot-Cold / Standard)     ║${N}\n"
printf "${B}║  $(date -u '+%Y-%m-%d %H:%M:%S UTC')                                         ║${N}\n"
printf "${B}╚══════════════════════════════════════════════════════════════╝${N}\n"
printf "  Server:   ${B}%s${N}\n" "$SERVER_URL"
printf "  Agent:    ${B}%s${N}\n" "$AGENT"
printf "  User:     ${B}%s${N}\n" "$USERNAME"
printf "  Results:  ${B}%s${N}\n" "$RESULT_FILE"

# ═══════════════════════════════════════════════════════════════════
#  0. HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════
hdr "0. HEALTH CHECK"
HEALTH=$(curl -s --max-time 10 "${SERVER_URL}/")
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
echo "$HEALTH" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('Azure Search Healthy') else 1)" 2>/dev/null \
  && ok "Azure Search healthy" || warn "Azure Search status unknown"

# ═══════════════════════════════════════════════════════════════════
#  Start markdown file
# ═══════════════════════════════════════════════════════════════════
cat > "$RESULT_FILE" <<EOF
# Three-Mode Comparison: None vs Hot/Cold vs Standard

**Date:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')
**Server:** $SERVER_URL
**Agent:** $AGENT
**User:** $USERNAME
**Image:** v21-restore-mem (shared memory layer restored to standard paths)

---

## Store Prompts — Timing (ms)

Each row sends one prompt through \`/compare\`, which runs all 3 modes sequentially.
Standard path now includes: Azure Search retrieve → agent.run() (invoking→LLM→invoked) → Event Hubs enqueue.

| # | Prompt | Mode | Retrieve | LLM | Enqueue | Total |
|---|--------|------|----------|-----|---------|-------|
EOF

# ═══════════════════════════════════════════════════════════════════
#  1. STORE PROMPTS
# ═══════════════════════════════════════════════════════════════════
hdr "1. STORE PROMPTS (10 prompts through /compare)"

# Store prompts in an array — read from heredoc to avoid escaping issues
STORE_PROMPTS=()
STORE_LABELS=()

STORE_LABELS+=("Arrival & Identity")
STORE_PROMPTS+=("Hi! My name is Derek, I'm 38 years old, and I just checked into room 412 with my partner Jamie. We're here from Seattle celebrating our 10th anniversary. We drove down in our Tesla and we'll be staying through Sunday with a late checkout. Can you suggest a welcome drink?")

STORE_LABELS+=("Dietary & Dining")
STORE_PROMPTS+=("For dinner planning this weekend — I'm allergic to shellfish and Jamie is lactose intolerant. We both love Mediterranean and Japanese cuisine. Last time we visited we had an amazing omakase at the resort restaurant and I'd love to do that again. Oh, and I take my coffee black, no sugar. Any breakfast recommendations?")

STORE_LABELS+=("Spa Preferences")
STORE_PROMPTS+=("I'd like to book some spa treatments. I prefer deep-tissue massages — no Swedish please. I'm also allergic to lavender so make sure none of the oils or products contain it. Jamie absolutely loves hot stone treatments and aromatherapy with eucalyptus. We'd like couples treatments on Saturday afternoon if available. What do you recommend?")

STORE_LABELS+=("Fitness & Wellness")
STORE_PROMPTS+=("I'm currently training for the Boston Marathon in April so I need to keep up my running schedule. I usually run 8 miles before 7 AM. I also do yoga in the evenings — I loved the ocean-view yoga session you offered last time I was here. Jamie prefers Pilates or swimming. Do you have a gym with treadmills and a pool?")

STORE_LABELS+=("Activities & Interests")
STORE_PROMPTS+=("We're big fans of water sports — Jamie is an advanced surfer and I'm an intermediate kayaker. We also enjoy hiking and we've done the coastal bluff trail here before. For something different this trip we'd love to try a sunset sailing excursion or a guided snorkeling tour. Is there anything like that available Saturday?")

STORE_LABELS+=("Work & Schedule")
STORE_PROMPTS+=("I work in software engineering and Jamie is a veterinarian. I might need to hop on a video call Saturday morning around 9 AM, so I'll need good Wi-Fi and a quiet spot. Other than that one call, we're completely unplugged this weekend. I'm normally an early riser but Jamie likes to sleep in until 9. Can you suggest a morning plan that works for both of us?")

STORE_LABELS+=("Past Visits & Loyalty")
STORE_PROMPTS+=("This is actually our third visit to the resort. The first time was in 2022 for a friend's wedding, and the second was last summer when I did the triathlon training camp. I'm a Gold tier loyalty member — member number LM-88421. Last visit the front desk upgraded us to an ocean-view suite and that was incredible. Is there any loyalty perk available this time?")

STORE_LABELS+=("Special Requests")
STORE_PROMPTS+=("A few room requests: we prefer extra firm pillows, Jamie needs a hypoallergenic duvet, and we'd love a mini-fridge stocked with sparkling water and oat milk. I also have a slight sensitivity to bright overhead lighting so if the room has dimmable lights that would be perfect. And could we get fresh flowers — anything except lavender of course. What do you have available?")

STORE_LABELS+=("Evening Plans")
STORE_PROMPTS+=("For Saturday night we want something special for our anniversary. We love live jazz, cocktail bars with craft menus, and outdoor seating. Budget isn't a huge concern — we're thinking a tasting-menu dinner followed by drinks somewhere atmospheric. We also enjoy stargazing if there are any dark-sky spots nearby. Can you put together an evening itinerary?")

STORE_LABELS+=("Departure & Follow-Up")
STORE_PROMPTS+=("On Sunday we'll need late checkout — ideally 2 PM if possible since our drive back to Seattle is about 4 hours. Before we leave we'd like to grab brunch somewhere with a good eggs benedict — mine without hollandaise since I prefer it with avocado instead. Also, can you send a summary of everything we booked to my email derek@example.com? And please save all my preferences for next time.")

# Accumulators for averages
NONE_TOTALS=()
HC_TOTALS=()
STD_TOTALS=()

for i in "${!STORE_PROMPTS[@]}"; do
  NUM=$((i + 1))
  LABEL="${STORE_LABELS[$i]}"
  PROMPT="${STORE_PROMPTS[$i]}"

  printf "  [%2d/10] %-22s " "$NUM" "$LABEL"

  RESPONSE=$(echo "$PROMPT" | call_compare_stdin)

  if echo "$RESPONSE" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    # Parse each mode
    for MODE in none hot_cold standard; do
      IFS='|' read -r RETRIEVE LLM ENQUEUE TOTAL <<< "$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
m = d.get('$MODE', {})
t = m.get('timing_ms', {})
print(f\"{t.get('memory_retrieve',0)}|{t.get('llm',0)}|{t.get('memory_enqueue',0)}|{t.get('total',0)}\")
" <<< "$RESPONSE" 2>/dev/null || echo "0|0|0|0")"

      case "$MODE" in
        none)     MODE_LABEL="None";     NONE_TOTALS+=("$TOTAL") ;;
        hot_cold) MODE_LABEL="Hot/Cold"; HC_TOTALS+=("$TOTAL") ;;
        standard) MODE_LABEL="Standard"; STD_TOTALS+=("$TOTAL") ;;
      esac

      echo "| $NUM | $LABEL | $MODE_LABEL | ${RETRIEVE} | ${LLM} | ${ENQUEUE} | ${TOTAL} |" >> "$RESULT_FILE"
    done

    # Print summary for this prompt
    NONE_T=$(python3 -c "import json; d=json.loads('''$RESPONSE'''); print(d['none']['timing_ms']['total'])" 2>/dev/null || echo "?")
    HC_T=$(python3 -c "import json; d=json.loads('''$RESPONSE'''); print(d['hot_cold']['timing_ms']['total'])" 2>/dev/null || echo "?")
    STD_T=$(python3 -c "import json; d=json.loads('''$RESPONSE'''); print(d['standard']['timing_ms']['total'])" 2>/dev/null || echo "?")
    printf "None=%sms  HC=%sms  Std=%sms\n" "$NONE_T" "$HC_T" "$STD_T"
    ok "Store prompt $NUM"
  else
    printf "ERROR\n"
    fail "Store prompt $NUM — bad response"
    echo "| $NUM | $LABEL | — | — | — | — | ERROR |" >> "$RESULT_FILE"
  fi

  # Small delay between prompts to avoid rate limiting
  sleep 2
done

# ═══════════════════════════════════════════════════════════════════
#  2. RECALL PROMPTS
# ═══════════════════════════════════════════════════════════════════
hdr "2. RECALL PROMPTS (10 recall queries through /compare)"

cat >> "$RESULT_FILE" <<'EOF'

---

## Recall Prompts — Timing & Memory Verification

| # | Recall Prompt | Mode | Retrieve | LLM | Enqueue | Total |
|---|---------------|------|----------|-----|---------|-------|
EOF

RECALL_PROMPTS=()
RECALL_LABELS=()
RECALL_KEYS=()

RECALL_LABELS+=("Identity Recall")
RECALL_PROMPTS+=("What do you know about me and my partner?")
RECALL_KEYS+=("Derek|Jamie|Seattle|anniversary|412")

RECALL_LABELS+=("Dining Recall")
RECALL_PROMPTS+=("We want to book dinner — what should you keep in mind?")
RECALL_KEYS+=("shellfish|lactose|Mediterranean|Japanese|omakase|black coffee")

RECALL_LABELS+=("Spa Recall")
RECALL_PROMPTS+=("Recommend spa treatments for both of us.")
RECALL_KEYS+=("deep.tissue|lavender|hot stone|eucalyptus|couples")

RECALL_LABELS+=("Fitness Recall")
RECALL_PROMPTS+=("Help me plan tomorrow morning's workout.")
RECALL_KEYS+=("marathon|8 mile|7 AM|yoga|Pilates|swimming")

RECALL_LABELS+=("Activities Recall")
RECALL_PROMPTS+=("What outdoor activities would we enjoy?")
RECALL_KEYS+=("kayak|surf|bluff|sailing|snorkel")

RECALL_LABELS+=("Schedule Recall")
RECALL_PROMPTS+=("I need a quiet spot Saturday morning — remember why?")
RECALL_KEYS+=("video call|9 AM|software|Wi-Fi|sleep")

RECALL_LABELS+=("Visit History Recall")
RECALL_PROMPTS+=("Have we been here before?")
RECALL_KEYS+=("third|3rd|2022|wedding|triathlon|Gold|LM-88421|ocean.view")

RECALL_LABELS+=("Room Prefs Recall")
RECALL_PROMPTS+=("Remind me what room preferences we set up.")
RECALL_KEYS+=("firm pillow|hypoallergenic|sparkling|oat milk|dim|flower|lavender")

RECALL_LABELS+=("Evening Recall")
RECALL_PROMPTS+=("Plan our anniversary evening.")
RECALL_KEYS+=("jazz|cocktail|outdoor|tasting|stargaz")

RECALL_LABELS+=("Checkout Recall")
RECALL_PROMPTS+=("What do we need for checkout day?")
RECALL_KEYS+=("2 PM|late checkout|Seattle|eggs benedict|avocado|derek@example")

cat >> "$RESULT_FILE" <<'EOF'
EOF

RECALL_NONE_HITS=0
RECALL_HC_HITS=0
RECALL_STD_HITS=0

for i in "${!RECALL_PROMPTS[@]}"; do
  NUM=$((i + 1))
  LABEL="${RECALL_LABELS[$i]}"
  PROMPT="${RECALL_PROMPTS[$i]}"
  KEYS="${RECALL_KEYS[$i]}"

  printf "  [R%d/10] %-22s " "$NUM" "$LABEL"

  RESPONSE=$(echo "$PROMPT" | call_compare_stdin)

  if echo "$RESPONSE" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    for MODE in none hot_cold standard; do
      IFS='|' read -r RETRIEVE LLM ENQUEUE TOTAL <<< "$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
m = d.get('$MODE', {})
t = m.get('timing_ms', {})
print(f\"{t.get('memory_retrieve',0)}|{t.get('llm',0)}|{t.get('memory_enqueue',0)}|{t.get('total',0)}\")
" <<< "$RESPONSE" 2>/dev/null || echo "0|0|0|0")"

      case "$MODE" in
        none)     MODE_LABEL="None" ;;
        hot_cold) MODE_LABEL="Hot/Cold" ;;
        standard) MODE_LABEL="Standard" ;;
      esac

      echo "| R$NUM | $LABEL | $MODE_LABEL | ${RETRIEVE} | ${LLM} | ${ENQUEUE} | ${TOTAL} |" >> "$RESULT_FILE"
    done

    # Check memory hits in each mode's response message
    for MODE in none hot_cold standard; do
      MSG=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('$MODE', {}).get('message', ''))
" <<< "$RESPONSE" 2>/dev/null || echo "")

      HITS=$(echo "$MSG" | grep -ciP "$KEYS" 2>/dev/null || echo "0")
      case "$MODE" in
        none)     [[ "$HITS" -gt 0 ]] && ((RECALL_NONE_HITS++)) ;;
        hot_cold) [[ "$HITS" -gt 0 ]] && ((RECALL_HC_HITS++)) ;;
        standard) [[ "$HITS" -gt 0 ]] && ((RECALL_STD_HITS++)) ;;
      esac
    done

    # Print summary
    STD_T=$(python3 -c "import json; d=json.loads('''$RESPONSE'''); print(d['standard']['timing_ms']['total'])" 2>/dev/null || echo "?")
    HC_T=$(python3 -c "import json; d=json.loads('''$RESPONSE'''); print(d['hot_cold']['timing_ms']['total'])" 2>/dev/null || echo "?")
    NONE_T=$(python3 -c "import json; d=json.loads('''$RESPONSE'''); print(d['none']['timing_ms']['total'])" 2>/dev/null || echo "?")
    printf "None=%sms  HC=%sms  Std=%sms\n" "$NONE_T" "$HC_T" "$STD_T"
    ok "Recall R$NUM"
  else
    printf "ERROR\n"
    fail "Recall R$NUM"
    echo "| R$NUM | $LABEL | — | — | — | — | ERROR |" >> "$RESULT_FILE"
  fi

  sleep 2
done

# ═══════════════════════════════════════════════════════════════════
#  3. AVERAGES & SUMMARY
# ═══════════════════════════════════════════════════════════════════
hdr "3. SUMMARY"

# Compute averages
avg() {
  local arr=("$@")
  local sum=0 count=${#arr[@]}
  [[ $count -eq 0 ]] && echo "0" && return
  for v in "${arr[@]}"; do sum=$((sum + v)); done
  echo $((sum / count))
}

NONE_AVG=$(avg "${NONE_TOTALS[@]}")
HC_AVG=$(avg "${HC_TOTALS[@]}")
STD_AVG=$(avg "${STD_TOTALS[@]}")

cat >> "$RESULT_FILE" <<EOF

---

## Summary

### Average Store Prompt Timing (ms)

| Mode | Avg Total |
|------|-----------|
| None | ${NONE_AVG} |
| Hot/Cold | ${HC_AVG} |
| Standard | ${STD_AVG} |

### Speed Ordering

EOF

# Determine ordering
if [[ $NONE_AVG -le $HC_AVG && $HC_AVG -le $STD_AVG ]]; then
  echo "✅ **Correct ordering: None (${NONE_AVG}ms) < Hot/Cold (${HC_AVG}ms) < Standard (${STD_AVG}ms)**" >> "$RESULT_FILE"
  ok "Speed ordering: None < Hot/Cold < Standard"
elif [[ $NONE_AVG -le $STD_AVG && $HC_AVG -le $STD_AVG ]]; then
  echo "⚠️ Standard is slowest (${STD_AVG}ms) but None (${NONE_AVG}ms) vs Hot/Cold (${HC_AVG}ms) ordering varies" >> "$RESULT_FILE"
  warn "Standard slowest but None/HC order varies"
else
  echo "❌ Unexpected ordering: None=${NONE_AVG}ms, Hot/Cold=${HC_AVG}ms, Standard=${STD_AVG}ms" >> "$RESULT_FILE"
  fail "Unexpected speed ordering"
fi

cat >> "$RESULT_FILE" <<EOF

### Recall Memory Hits (out of 10)

| Mode | Recall Hits |
|------|-------------|
| None | ${RECALL_NONE_HITS}/10 |
| Hot/Cold | ${RECALL_HC_HITS}/10 |
| Standard | ${RECALL_STD_HITS}/10 |

### Test Results

| Metric | Count |
|--------|-------|
| ✅ PASS | $PASS |
| ❌ FAIL | $FAIL |
| ⚠️ WARN | $WARN |
| **Total** | **$((PASS + FAIL + WARN))** |

---

*Generated by compare_modes.sh on $(date -u '+%Y-%m-%d %H:%M:%S UTC')*
EOF

printf "\n  ${B}Results:${N} %s\n" "$RESULT_FILE"
printf "  ${G}PASS: %d${N}  ${R}FAIL: %d${N}  ${Y}WARN: %d${N}\n\n" "$PASS" "$FAIL" "$WARN"
