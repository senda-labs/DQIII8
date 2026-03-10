#!/usr/bin/env bash
# JARVIS — Comando de entrada con routing de 3 niveles
#
# NIVEL 1 — Ollama (gratis)
#   j local "prompt"   → ollama_wrapper.py directo
#   j local            → claude con system prompt para delegar código
#
# NIVEL 2 — Haiku (barato)
#   j review "prompt"  → claude haiku con prompt
#   j review           → claude haiku interactivo
#
# NIVEL 3 — Sonnet (potente)
#   j                  → claude sonnet normal
#   j finance          → claude sonnet, contexto financiero
#   j novel            → claude sonnet, contexto xianxia/narrativa

JARVIS_ROOT="${JARVIS_ROOT:-/root/jarvis}"
OLLAMA_WRAPPER="$JARVIS_ROOT/bin/ollama_wrapper.py"
MODEL_HAIKU="claude-haiku-4-5-20251001"
MODEL_SONNET="claude-sonnet-4-6"

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
      exec claude --append-system-prompt \
        "Eres JARVIS en modo local. Para tareas de código Python (refactoring, debugging, implementación, explicaciones técnicas), ejecuta el siguiente comando de shell y muestra su output al usuario: python3 $OLLAMA_WRAPPER '<prompt>'. Reserva Claude para arquitectura, seguridad y decisiones de alto nivel."
    fi
    ;;

  # ── NIVEL 2: Haiku ────────────────────────────────────────────────
  review)
    echo "[JARVIS] Modo: review | Modelo: haiku-4-5 | Coste: bajo"
    echo "---"
    if [[ -n "$prompt" ]]; then
      exec claude --model "$MODEL_HAIKU" -p "$prompt"
    else
      exec claude --model "$MODEL_HAIKU"
    fi
    ;;

  # ── NIVEL 3: Sonnet ───────────────────────────────────────────────
  finance)
    echo "[JARVIS] Modo: finance | Modelo: sonnet-4-6 | Coste: normal"
    echo "---"
    exec claude --model "$MODEL_SONNET" --append-system-prompt \
      "Eres JARVIS en modo finance. Especializado en análisis financiero: WACC, DCF, valoración, modelos Excel, gráficos. Responde con rigor cuantitativo."
    ;;

  novel|creative)
    echo "[JARVIS] Modo: novel | Modelo: sonnet-4-6 | Coste: normal"
    echo "---"
    exec claude --model "$MODEL_SONNET" --append-system-prompt \
      "Eres JARVIS en modo creativo. Especializado en narrativa, novela xianxia, diálogos y worldbuilding. Usa em-dash (—) para diálogos. Mantén coherencia de tiempo verbal dentro de cada escena."
    ;;

  "")
    echo "[JARVIS] Modo: sonnet | Modelo: sonnet-4-6 | Coste: normal"
    echo "---"
    exec claude --model "$MODEL_SONNET"
    ;;

  *)
    echo "Uso: j [modo] [prompt]"
    echo ""
    echo "  NIVEL 1 — Gratis (Ollama local)"
    echo "    j local \"prompt\"   → qwen2.5-coder:7b directo"
    echo "    j local            → claude con delegación a Ollama"
    echo ""
    echo "  NIVEL 2 — Barato (Haiku)"
    echo "    j review \"prompt\"  → haiku-4-5 con prompt"
    echo "    j review           → haiku-4-5 interactivo"
    echo ""
    echo "  NIVEL 3 — Potente (Sonnet)"
    echo "    j                  → sonnet-4-6 normal"
    echo "    j finance          → sonnet-4-6, análisis financiero"
    echo "    j novel            → sonnet-4-6, escritura creativa"
    exit 1
    ;;
esac
