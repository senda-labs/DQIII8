#!/usr/bin/env bash
# JARVIS — Routing unificado 3 tiers
#
# Uso:
#   j [--model local|groq|sonnet] [PROMPT]
#   j --status        → proyecto, modelo activo, ollama ps, tmux sessions
#   j --audit         → Gemini code review (check-only)
#   j --classify TEXT → muestra qué tier manejaría el prompt
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
        --help|-h)
            cat <<EOF
JARVIS — 3-tier routing

  j [--model local|groq|sonnet] [PROMPT]
  j --status              proyecto + modelo + ollama ps + tmux
  j --audit               Gemini code review (check-only)
  j --classify TEXTO      muestra tier para el prompt dado

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
        echo "[JARVIS] Tier 3 — Claude $MODEL_SONNET | Coste: normal" >&2
        cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT"
        ;;

    *)
        echo "[JARVIS] Error: modelo desconocido '$MODEL'. Usa: local, groq, sonnet" >&2
        exit 1
        ;;
esac
