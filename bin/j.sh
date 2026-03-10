#!/usr/bin/env bash
# JARVIS — Comando de entrada
# Uso:
#   j             → claude (Sonnet, modo normal)
#   j local       → claude con contexto ollama para código
#   j finance     → claude directo (análisis financiero)
#   j novel       → claude directo (escritura creativa)

JARVIS_ROOT="${JARVIS_ROOT:-/root/jarvis}"
MODEL_SONNET="claude-sonnet-4-6"
MODEL_LOCAL="qwen2.5-coder:7b (via Ollama)"

mode="${1:-}"

case "$mode" in
  local)
    echo "Modelo activo: $MODEL_LOCAL  →  tareas de código delegadas a Ollama"
    echo "Tip: para queries directas → echo 'prompt' | python3 $JARVIS_ROOT/bin/ollama_wrapper.py"
    echo "---"
    exec claude --append-system-prompt \
      "Eres JARVIS en modo local. Para tareas de código Python, refactoring, debugging y explicaciones técnicas, delega a Ollama ejecutando: echo '<prompt>' | python3 $JARVIS_ROOT/bin/ollama_wrapper.py  Usa Claude solo para arquitectura, seguridad y decisiones de alto nivel."
    ;;
  finance)
    echo "Modelo activo: $MODEL_SONNET  →  modo análisis financiero"
    echo "---"
    exec claude --append-system-prompt \
      "Eres JARVIS en modo finance. Especializado en análisis financiero: WACC, DCF, valoración, modelos Excel, gráficos. Responde con rigor cuantitativo."
    ;;
  novel|creative)
    echo "Modelo activo: $MODEL_SONNET  →  modo escritura creativa"
    echo "---"
    exec claude --append-system-prompt \
      "Eres JARVIS en modo creativo. Especializado en narrativa, novela xianxia, diálogos y worldbuilding. Usa em-dash (—) para diálogos. Mantén coherencia de tiempo verbal dentro de cada escena."
    ;;
  "")
    echo "Modelo activo: $MODEL_SONNET"
    echo "---"
    exec claude
    ;;
  *)
    echo "Uso: j [local|finance|novel]"
    echo "  (sin args)  → Sonnet, modo normal"
    echo "  local       → Sonnet + delega código a Ollama qwen2.5-coder:7b"
    echo "  finance     → Sonnet, análisis financiero"
    echo "  novel       → Sonnet, escritura creativa"
    exit 1
    ;;
esac
