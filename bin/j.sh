#!/usr/bin/env bash
# DQIII8 — Unified 3-tier routing
#
# Usage:
#   j [--model local|groq|sonnet] [PROMPT]
#   j --status        → project, active model, ollama ps, tmux sessions
#   j --audit         → Gemini code review (check-only)
#   j --classify TEXT → shows which tier would handle the prompt
#   j --autonomous    → activates JARVIS_MODE=autonomous and launches claude
#   j --loop PROJECT [CYCLES] [TIER] → OrchestratorLoop (tier1/tier2/tier3/haiku)
#   j --benchmark-report → Sonnet comparative report of tiers
#
# Tiers:
#   local  → Tier 1: Ollama qwen2.5-coder:7b  (free, local)
#             Fallback if Ollama not responding: openrouter/qwen3-235b-a22b:free
#   groq   → Tier 2: Groq llama-3.3-70b-versatile (free, cloud)
#   sonnet → Tier 3: Claude Sonnet 4.6  (paid, powerful) [default]

set -euo pipefail

JARVIS_ROOT="${JARVIS_ROOT:-/root/jarvis}"
OR_WRAPPER="$JARVIS_ROOT/bin/openrouter_wrapper.py"
MODEL_SONNET="claude-sonnet-4-6"
OLLAMA_MODEL="qwen2.5-coder:7b"
OLLAMA_FALLBACK="qwen/qwen3-235b-a22b:free"

# Load environment variables
[[ -f "$JARVIS_ROOT/.env" ]] && set -a && source "$JARVIS_ROOT/.env" && set +a

# Environment validation
python3 "$(dirname "$0")/validate_env.py" || echo "[warn] Environment check failed"

# Flag A/B: purpose active if .jarvis_proposito exists
# Enable: touch /root/jarvis/.jarvis_proposito
# Disable: rm /root/jarvis/.jarvis_proposito
if [[ -f "$JARVIS_ROOT/.jarvis_proposito" ]]; then
    export JARVIS_PROPOSITO=1
else
    export JARVIS_PROPOSITO=0
fi

check_deps() {
    python3 --version > /dev/null 2>&1 || { echo "❌ Python3 not found"; exit 1; }
    ollama list > /dev/null 2>&1 || echo "⚠️  Ollama not responding — using Tier 2/3 only"
    [ -f "$JARVIS_ROOT/.env" ] || { echo "❌ .env not found in $JARVIS_ROOT"; exit 1; }
    # Anthropic key is optional — only required when DQ_DEFAULT_TIER=auto and user calls Tier A
    _dq_tier="${DQ_DEFAULT_TIER:-auto}"
    if [[ "$_dq_tier" == "auto" || "$_dq_tier" == "" ]] && [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
        echo "⚠️  ANTHROPIC_API_KEY not defined — Tier A/S/S+ unavailable. Run: dq --setup"
    fi
    echo "✅ System OK — starting DQIII8"
}

MODEL="sonnet"

show_status() {
    echo "=== DQIII8 Status ==="
    echo "Project  : $(basename "$JARVIS_ROOT")"
    echo "Modelo   : $MODEL_SONNET"
    echo "Tier     : 3 (sonnet) | 2 (groq) | 1 (ollama)"
    echo ""
    echo "── Ollama ──"
    ollama ps 2>/dev/null || echo "(not available)"
    echo ""
    echo "── tmux sessions ──"
    tmux ls 2>/dev/null || echo "(none)"
    echo ""
    python3 "$JARVIS_ROOT/bin/subscription.py" 2>/dev/null || echo "(subscription unavailable)"
}

ollama_available() {
    ollama ps &>/dev/null && ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"
}

# ── Early flags — run before full env check ──────────────────────────────────
case "${1:-}" in
    --setup)
        shift
        exec python3 "$JARVIS_ROOT/bin/setup_wizard.py" "$@"
        ;;
    --set-groq)
        if [ -z "${2:-}" ]; then
            echo "Usage: dq --set-groq gsk_YOUR_KEY"
            exit 1
        fi
        chmod 600 "$JARVIS_ROOT/.env" 2>/dev/null || true
        if grep -q "^GROQ_API_KEY=" "$JARVIS_ROOT/.env" 2>/dev/null; then
            sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$2|" "$JARVIS_ROOT/.env"
        else
            echo "GROQ_API_KEY=$2" >> "$JARVIS_ROOT/.env"
        fi
        chmod 600 "$JARVIS_ROOT/.env"
        echo "✓ Groq API key configured. Tier B now available."
        exit 0
        ;;
    --set-anthropic)
        if [ -z "${2:-}" ]; then
            echo "Usage: dq --set-anthropic sk-ant-YOUR_KEY"
            exit 1
        fi
        chmod 600 "$JARVIS_ROOT/.env" 2>/dev/null || true
        if grep -q "^ANTHROPIC_API_KEY=" "$JARVIS_ROOT/.env" 2>/dev/null; then
            sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$2|" "$JARVIS_ROOT/.env"
        else
            echo "ANTHROPIC_API_KEY=$2" >> "$JARVIS_ROOT/.env"
        fi
        chmod 600 "$JARVIS_ROOT/.env"
        echo "✓ Anthropic API key configured. Tiers A/S/S+ now available."
        exit 0
        ;;
esac

check_deps

# ── ENABLE_TOOL_SEARCH: false when ANTHROPIC_BASE_URL points to a proxy ────
_base_url="${ANTHROPIC_BASE_URL:-}"
if [[ -z "$_base_url" || "$_base_url" =~ ^https?://(api\.)?anthropic\.com ]]; then
    export ENABLE_TOOL_SEARCH="auto"
else
    export ENABLE_TOOL_SEARCH="false"
    _proxy_host="$(echo "$_base_url" | awk -F/ '{print $3}')"
    echo "[DQIII8] Proxy detected ($_proxy_host) — ENABLE_TOOL_SEARCH=false" >&2
fi

# ── Flag parsing ─────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model|-m)
            MODEL="$2"
            shift 2
            ;;
        --status)
            show_status
            exit 0
            ;;
        --audit)
            exec python3 "$JARVIS_ROOT/bin/auditor_local.py"
            ;;
        --setup)
            exec python3 "$JARVIS_ROOT/bin/setup_wizard.py"
            ;;
        --set-groq|--set-anthropic)
            # Already handled above; reaching here means they were passed after other flags
            echo "Error: --set-groq / --set-anthropic must be the first argument." >&2
            exit 1
            ;;
        --classify|-c)
            shift
            exec python3 "$OR_WRAPPER" classify "$*"
            ;;
        --autonomous)
            # j --autonomous "objective" [max_hours]
            # Delegates to autonomous_loop.sh (3-layer supervisor active)
            shift
            OBJECTIVE="${1:-}"
            MAX_HOURS="${2:-8}"
            exec bash "$JARVIS_ROOT/bin/autonomous_loop.sh" "$OBJECTIVE" "$MAX_HOURS"
            ;;
        loop)
            # j loop → starts Claude Code as jarvis user (non-root)
            # PermissionAnalyzer active via hooks — without dangerously-skip-permissions
            if [[ "${2:-}" == "" || "${2:-}" == "auth" ]]; then
                echo "[DQIII8] Claude Code as jarvis user (non-root)"
                echo "  PermissionAnalyzer active via hooks"
                echo "  To authenticate: /login"
                exec su - jarvis -c "
                    export JARVIS_ROOT='/root/jarvis'
                    export JARVIS_MODE='autonomous'
                    cd /root/math-image-generator
                    claude --add-dir /root/jarvis \
                           --add-dir /root/math-image-generator
                "
            fi
            ;;
        --loop)
            PROJECT="${2:-my-project}"
            CYCLES="${3:-10}"
            TIER="tier3"
            for i in "$@"; do
                if [[ "$i" == tier* ]]; then
                    TIER="$i"
                fi
            done
            echo "[DQIII8] Loop → $PROJECT | $CYCLES cycles | model: $TIER" >&2
            JARVIS_MODE=autonomous python3 "$JARVIS_ROOT/bin/orchestrator_loop.py" \
                --project "$PROJECT" --cycles "$CYCLES" --tier "$TIER"
            exit 0
            ;;
        --benchmark-report)
            echo "[DQIII8] Generating benchmark report with Sonnet..." >&2
            REPORT=$(python3 -c "
import sqlite3, json
from pathlib import Path
DB = Path('$JARVIS_ROOT/database/jarvis_metrics.db')
conn = sqlite3.connect(str(DB))
results = conn.execute('SELECT * FROM benchmark_results').fetchall()
conn.close()
print(json.dumps([list(r) for r in results], indent=2))
")
            echo "$REPORT" | claude --headless -p "
You are the DQIII8 auditor. Analyze these benchmark results
of AI models executing programming tasks autonomously.

DATA:
$REPORT

Generate an executive report comparing:
1. Success rate by tier
2. Speed (average duration per objective)
3. What types of tasks each tier handles best
4. Recommendation: which tier to use by default for OrchestratorLoop?

Be specific and use the actual data."
            exit 0
            ;;
        --harvest)
            shift
            exec python3 "$JARVIS_ROOT/bin/paper_harvester.py" "$@"
            ;;
        --upload|-u)
            shift
            exec python3 "$JARVIS_ROOT/bin/knowledge_upload.py" "$@"
            ;;
        --dashboard)
            shift
            exec python3 "$JARVIS_ROOT/bin/dashboard.py" "$@"
            ;;
        --help|-h)
            cat <<EOF
DQIII8 — 3-tier routing

  j [--model local|groq|sonnet] [PROMPT]
  j --status              proyecto + modelo + ollama ps + tmux
  j --audit               Local health audit (no LLM, Tier C compatible)
  j --setup               Interactive setup wizard (keys + default tier)
  j --set-groq KEY        Set Groq API key in .env (one command)
  j --set-anthropic KEY   Set Anthropic API key in .env (one command)
  j --classify TEXT       show tier for the given prompt
  j --autonomous "objective" [h]  autonomous mode with 3-layer supervisor (def. 8h)
  j --loop PROJECT [N] [TIER]   OrchestratorLoop: tier1/tier2/tier3/haiku (def. tier3)
  j --benchmark-report         Sonnet report comparing tiers
  j --upload FILE [--agent A] [--domain D]  upload knowledge file (PDF/MD/TXT/DOCX/ZIP)
  j --dashboard [--host H] [--port P]       web dashboard (localhost:8080 by default)
  j --harvest [--domain D] [--agent A] [--all] [--prune]  harvest papers from arXiv + Semantic Scholar

Tiers:
  local   Tier 1 — Ollama $OLLAMA_MODEL (free, local)
  groq    Tier 2 — Groq llama-3.3-70b-versatile (free, cloud)
  sonnet  Tier 3 — Claude Sonnet 4.6 (paid, powerful) [default]
EOF
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

# ── Routing ──────────────────────────────────────────────────────────────────
case "$MODEL" in

    local|ollama)
        echo "[DQIII8] Tier 1 — Ollama $OLLAMA_MODEL | Cost: \$0" >&2
        if ollama_available; then
            exec claude --model "ollama:$OLLAMA_MODEL" "$@"
        else
            echo "[DQIII8] Ollama unavailable → fallback openrouter/$OLLAMA_FALLBACK" >&2
            exec python3 "$OR_WRAPPER" --model "$OLLAMA_FALLBACK" "$@"
        fi
        ;;

    groq)
        echo "[DQIII8] Tier 2 — Groq llama-3.3-70b-versatile | Cost: free" >&2
        exec python3 "$OR_WRAPPER" --agent git-specialist "$@"
        ;;

    sonnet|"")
        # Respect DQ_DEFAULT_TIER when no explicit --model flag was given
        _dq_default="${DQ_DEFAULT_TIER:-auto}"
        if [[ "$_dq_default" == "groq-only" || "$_dq_default" == "groq+ollama" ]]; then
            echo "[DQIII8] DQ_DEFAULT_TIER=$_dq_default → Tier 2 (Groq, free)" >&2
            exec python3 "$OR_WRAPPER" --agent git-specialist "$@"
        elif [[ "$_dq_default" == "ollama-only" ]]; then
            echo "[DQIII8] DQ_DEFAULT_TIER=$_dq_default → Tier 1 (Ollama, local)" >&2
            if ollama_available; then
                exec claude --model "ollama:$OLLAMA_MODEL" "$@"
            else
                echo "[DQIII8] Ollama unavailable → fallback openrouter/$OLLAMA_FALLBACK" >&2
                exec python3 "$OR_WRAPPER" --model "$OLLAMA_FALLBACK" "$@"
            fi
        fi
        # auto (or unset) → default Sonnet behaviour
        _router_out="$(python3 "$JARVIS_ROOT/bin/model_router.py" "código" 2>/dev/null || true)"
        echo "[DQIII8] Tier 3 — Claude $MODEL_SONNET | Cost: standard" >&2
        [[ -n "$_router_out" ]] && echo "[DQIII8] Active model: $_router_out" >&2
        cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT"
        ;;

    *)
        echo "[DQIII8] Error: unknown model '$MODEL'. Use: local, groq, sonnet" >&2
        exit 1
        ;;
esac
