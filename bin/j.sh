#!/usr/bin/env bash
# JARVIS — Comando de entrada con routing de 4 niveles
#
# NIVEL 1 — Ollama (gratis, local)
#   j local "prompt"      → ollama_wrapper.py directo
#   j local               → claude con system prompt para delegar código
#
# NIVEL 2 — OpenRouter (gratis, cloud)
#   j code "prompt"       → python-specialist (qwen3-coder-480b)
#   j research "tema"     → research-analyst (step-3.5-flash)
#   j review "código"     → code-reviewer (gpt-oss-120b)
#   j creative "prompt"   → creative-writer (llama-3.3-70b)
#
# NIVEL 3 — Sonnet (potente, pago)
#   j                     → claude sonnet normal
#   j finance             → claude sonnet, contexto financiero
#   j novel               → claude sonnet, contexto xianxia/narrativa

JARVIS_ROOT="${JARVIS_ROOT:-/root/jarvis}"
OLLAMA_WRAPPER="$JARVIS_ROOT/bin/ollama_wrapper.py"
OR_WRAPPER="$JARVIS_ROOT/bin/openrouter_wrapper.py"
MODEL_SONNET="claude-sonnet-4-6"

# Cargar variables de entorno desde .env si existe
[[ -f "$JARVIS_ROOT/.env" ]] && set -a && source "$JARVIS_ROOT/.env" && set +a

mode="${1:-}"
shift 2>/dev/null
prompt="$*"

case "$mode" in

  # ── NIVEL 1: Ollama ────────────────────────────────────────────────
  local)
    echo "[JARVIS] Modo: local | Modelo: qwen2.5-coder:7b | Coste: \$0"
    echo "---"
    if [[ -n "$prompt" ]]; then
      exec python3 "$OLLAMA_WRAPPER" "$prompt"
    else
      cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT" \
        --append-system-prompt \
        "Eres JARVIS en modo local. Para código Python simple usa: python3 $OLLAMA_WRAPPER '<prompt>'. Reserva Sonnet para arquitectura y decisiones complejas."
    fi
    ;;

  # ── NIVEL 2: OpenRouter ───────────────────────────────────────────
  code)
    echo "[JARVIS] Modo: code | Agente: python-specialist | Provider: OpenRouter" >&2
    echo "---" >&2
    if [[ -n "$prompt" ]]; then
      exec python3 "$OR_WRAPPER" --agent python-specialist "$prompt"
    else
      exec python3 "$OR_WRAPPER" --agent python-specialist
    fi
    ;;

  research)
    echo "[JARVIS] Modo: research | Agente: research-analyst | Provider: OpenRouter" >&2
    echo "---" >&2
    if [[ -n "$prompt" ]]; then
      exec python3 "$OR_WRAPPER" --agent research-analyst "$prompt"
    else
      exec python3 "$OR_WRAPPER" --agent research-analyst
    fi
    ;;

  review)
    echo "[JARVIS] Modo: review | Agente: code-reviewer | Provider: OpenRouter" >&2
    echo "---" >&2
    if [[ -n "$prompt" ]]; then
      exec python3 "$OR_WRAPPER" --agent code-reviewer "$prompt"
    else
      exec python3 "$OR_WRAPPER" --agent code-reviewer
    fi
    ;;

  creative)
    echo "[JARVIS] Modo: creative | Agente: creative-writer | Provider: OpenRouter" >&2
    echo "---" >&2
    if [[ -n "$prompt" ]]; then
      exec python3 "$OR_WRAPPER" --agent creative-writer "$prompt"
    else
      exec python3 "$OR_WRAPPER" --agent creative-writer
    fi
    ;;

  # ── NIVEL 3: Sonnet ───────────────────────────────────────────────
  finance)
    echo "[JARVIS] Modo: finance | Modelo: sonnet-4-6 | Coste: normal"
    echo "---"
    cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT" \
      --append-system-prompt \
      "Eres JARVIS en modo finance. Especializado en análisis financiero: WACC, DCF, valoración, modelos Excel, gráficos. Responde con rigor cuantitativo."
    ;;

  novel)
    echo "[JARVIS] Modo: novel | Modelo: sonnet-4-6 | Coste: normal"
    echo "---"
    cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT" \
      --append-system-prompt \
      "Eres JARVIS en modo creativo. Especializado en narrativa, novela xianxia, diálogos y worldbuilding. Usa em-dash (—) para diálogos. Mantén coherencia de tiempo verbal dentro de cada escena."
    ;;

  "")
    echo "[JARVIS] Modo: sonnet | Modelo: sonnet-4-6 | Coste: normal"
    echo "---"
    cd "$JARVIS_ROOT" && exec claude --model "$MODEL_SONNET" --add-dir "$JARVIS_ROOT"
    ;;

  *)
    echo "Uso: j [modo] [prompt]"
    echo ""
    echo "  NIVEL 1 — Gratis (Ollama local)"
    echo "    j local \"prompt\"      → qwen2.5-coder:7b directo"
    echo "    j local               → claude con delegación a Ollama"
    echo ""
    echo "  NIVEL 2 — Gratis (OpenRouter cloud)"
    echo "    j code \"prompt\"       → python-specialist (qwen3-coder-480b)"
    echo "    j research \"tema\"     → research-analyst (step-3.5-flash)"
    echo "    j review \"código\"     → code-reviewer (gpt-oss-120b)"
    echo "    j creative \"prompt\"   → creative-writer (llama-3.3-70b)"
    echo ""
    echo "  NIVEL 3 — Potente (Sonnet)"
    echo "    j                     → sonnet-4-6 normal"
    echo "    j finance             → sonnet-4-6, análisis financiero"
    echo "    j novel               → sonnet-4-6, escritura creativa (xianxia)"
    exit 1
    ;;
esac
