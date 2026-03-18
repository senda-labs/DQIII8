#!/usr/bin/env bash
# JARVIS — Routing unificado 3 tiers
#
# Uso:
#   j [--model local|groq|sonnet] [PROMPT]
#   j --status        → proyecto, modelo activo, ollama ps, tmux sessions
#   j --audit         → Gemini code review (check-only)
#   j --classify TEXT → muestra qué tier manejaría el prompt
#   j --autonomous    → activa JARVIS_MODE=autonomous y lanza claude
#   j --loop PROJECT [CYCLES] [TIER] → OrchestratorLoop (tier1/tier2/tier3/haiku)
#   j --benchmark-report → informe Sonnet comparativo de tiers
#
# Tiers:
#   local  → Tier 1: Ollama qwen2.5-coder:7b  (gratis, local)
#             Fallback si Ollama no responde: openrouter/qwen3-235b-a22b:free
#   groq   → Tier 2: Groq llama-3.3-70b-versatile (gratis, cloud)
#   sonnet → Tier 3: Claude Sonnet 4.6  (pago, potente) [default]

set -euo pipefail

JARVIS_ROOT="${JARVIS_ROOT:-/root/jarvis}"
OR_WRAPPER="$JARVIS_ROOT/bin/openrouter_wrapper.py"
MODEL_SONNET="claude-sonnet-4-6"
OLLAMA_MODEL="qwen2.5-coder:7b"
OLLAMA_FALLBACK="qwen/qwen3-235b-a22b:free"

# Cargar variables de entorno
[[ -f "$JARVIS_ROOT/.env" ]] && set -a && source "$JARVIS_ROOT/.env" && set +a

# Flag A/B: propósito activo si existe .jarvis_proposito
# Activar: touch /root/jarvis/.jarvis_proposito
# Desactivar: rm /root/jarvis/.jarvis_proposito
if [[ -f "$JARVIS_ROOT/.jarvis_proposito" ]]; then
    export JARVIS_PROPOSITO=1
else
    export JARVIS_PROPOSITO=0
fi

check_deps() {
    python3 --version > /dev/null 2>&1 || { echo "❌ Python3 no encontrado"; exit 1; }
    ollama list > /dev/null 2>&1 || echo "⚠️  Ollama no responde — usando solo Tier 2/3"
    [ -f "$JARVIS_ROOT/.env" ] || { echo "❌ .env no encontrado en $JARVIS_ROOT"; exit 1; }
    [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "❌ ANTHROPIC_API_KEY no definida"; exit 1; }
    echo "✅ Sistema OK — arrancando JARVIS"
}

MODEL="sonnet"

show_status() {
    echo "=== JARVIS Status ==="
    echo "Proyecto : $(basename "$JARVIS_ROOT")"
    echo "Modelo   : $MODEL_SONNET"
    echo "Tier     : 3 (sonnet) | 2 (groq) | 1 (ollama)"
    echo ""
    echo "── Ollama ──"
    ollama ps 2>/dev/null || echo "(no disponible)"
    echo ""
    echo "── tmux sessions ──"
    tmux ls 2>/dev/null || echo "(ninguna)"
}

ollama_available() {
    ollama ps &>/dev/null && ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"
}

check_deps

# ── ENABLE_TOOL_SEARCH: false cuando ANTHROPIC_BASE_URL apunta a un proxy ───
_base_url="${ANTHROPIC_BASE_URL:-}"
if [[ -z "$_base_url" || "$_base_url" =~ ^https?://(api\.)?anthropic\.com ]]; then
    export ENABLE_TOOL_SEARCH="auto"
else
    export ENABLE_TOOL_SEARCH="false"
    _proxy_host="$(echo "$_base_url" | awk -F/ '{print $3}')"
    echo "[JARVIS] Proxy detectado ($_proxy_host) — ENABLE_TOOL_SEARCH=false" >&2
fi

# ── Parseo de flags ──────────────────────────────────────────────────────────
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
            exec python3 "$JARVIS_ROOT/bin/gemini_review.py" --check-only
            ;;
        --classify|-c)
            shift
            exec python3 "$OR_WRAPPER" classify "$*"
            ;;
        --autonomous)
            export JARVIS_MODE=autonomous
            echo "  [JARVIS] Modo autónomo activado" >&2
            # Launch watchdog in background
            python3 "$JARVIS_ROOT/bin/autonomous_watchdog.py" &
            echo $! > /tmp/jarvis_watchdog.pid
            echo "  [JARVIS] Watchdog PID=$(cat /tmp/jarvis_watchdog.pid)" >&2
            shift
            ;;
        loop)
            # j loop → arranca Claude Code como usuario jarvis (non-root)
            # PermissionAnalyzer activo via hooks — sin dangerously-skip-permissions
            if [[ "${2:-}" == "" || "${2:-}" == "auth" ]]; then
                echo "[JARVIS] Claude Code como usuario jarvis (non-root)"
                echo "  PermissionAnalyzer activo via hooks"
                echo "  Para autenticar: /login"
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
            PROJECT="${2:-content-automation}"
            CYCLES="${3:-10}"
            TIER="tier3"
            for i in "$@"; do
                if [[ "$i" == tier* ]]; then
                    TIER="$i"
                fi
            done
            echo "[JARVIS] Loop → $PROJECT | $CYCLES ciclos | modelo: $TIER" >&2
            JARVIS_MODE=autonomous python3 "$JARVIS_ROOT/bin/orchestrator_loop.py" \
                --project "$PROJECT" --cycles "$CYCLES" --tier "$TIER"
            exit 0
            ;;
        --benchmark-report)
            echo "[JARVIS] Generando informe de benchmark con Sonnet..." >&2
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
Eres el auditor de JARVIS. Analiza estos resultados de benchmark
de modelos IA ejecutando tareas de programación de forma autónoma.

DATOS:
$REPORT

Genera un informe ejecutivo comparando:
1. Tasa de éxito por tier
2. Velocidad (duración media por objetivo)
3. Qué tipos de tareas resuelve mejor cada tier
4. Recomendación: ¿qué tier usar por defecto para el OrchestratorLoop?

Sé específico y usa los datos reales."
            exit 0
            ;;
        --help|-h)
            cat <<EOF
JARVIS — 3-tier routing

  j [--model local|groq|sonnet] [PROMPT]
  j --status              proyecto + modelo + ollama ps + tmux
  j --audit               Gemini code review (check-only)
  j --classify TEXTO      muestra tier para el prompt dado
  j --autonomous          activa modo autónomo (JARVIS_MODE=autonomous)
  j --loop PROJECT [N] [TIER]  OrchestratorLoop: tier1/tier2/tier3/haiku (def. tier3)
  j --benchmark-report         informe Sonnet comparando tiers

Tiers:
  local   Tier 1 — Ollama $OLLAMA_MODEL (gratis, local)
  groq    Tier 2 — Groq llama-3.3-70b-versatile (gratis, cloud)
  sonnet  Tier 3 — Claude Sonnet 4.6 (pago, potente) [default]
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
        echo "[JARVIS] Tier 1 — Ollama $OLLAMA_MODEL | Coste: \$0" >&2
        if ollama_available; then
            exec claude --model "ollama:$OLLAMA_MODEL" "$@"
        else
            echo "[JARVIS] Ollama no disponible → fallback openrouter/$OLLAMA_FALLBACK" >&2
            exec python3 "$OR_WRAPPER" --model "$OLLAMA_FALLBACK" "$@"
        fi
        ;;

    groq)
        echo "[JARVIS] Tier 2 — Groq llama-3.3-70b-versatile | Coste: free" >&2
        exec python3 "$OR_WRAPPER" --agent git-specialist "$@"
        ;;

    sonnet|"")
        _router_out="$(python3 "$JARVIS_ROOT/bin/model_router.py" "código" 2>/dev/null || true)"
        echo "[JARVIS] Tier 3 — Claude $MODEL_SONNET | Coste: normal" >&2
        [[ -n "$_router_out" ]] && echo "[JARVIS] Modelo activo: $_router_out" >&2
        cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT"
        ;;

    *)
        echo "[JARVIS] Error: modelo desconocido '$MODEL'. Usa: local, groq, sonnet" >&2
        exit 1
        ;;
esac
