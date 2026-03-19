#!/usr/bin/env python3
"""
DQIII8 — Ollama Wrapper
Envía un prompt a Ollama y hace streaming limpio de la respuesta.

Uso:
    echo "escribe factorial en Python" | python3 bin/ollama_wrapper.py
    python3 bin/ollama_wrapper.py --model llama3 "explica qué es un closure"
    python3 bin/ollama_wrapper.py "lista de sorting algorithms"
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

OLLAMA_URL = "http://localhost:11434/api/generate"  # nosemgrep
DEFAULT_MODEL = "qwen2.5-coder:7b"

# Ollama runs locally — HTTP to localhost is intentional (no TLS support)
_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _validate_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith(f".{h}") for h in _ALLOWED_HOSTS):
        raise ValueError(f"URL no permitida: {url}")


def stream_response(model: str, prompt: str) -> int:
    _validate_url(OLLAMA_URL)
    payload = json.dumps({"model": model, "prompt": prompt, "stream": True}).encode("utf-8")
    req = urllib.request.Request(  # nosemgrep
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosemgrep
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    print(token, end="", flush=True)
                if chunk.get("done"):
                    print()  # newline final
                    break
    except urllib.error.URLError as e:
        print(f"[ollama_wrapper] Error al conectar con Ollama: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envía un prompt a Ollama y hace streaming de la respuesta."
    )
    parser.add_argument(
        "--model",
        "-m",
        default=DEFAULT_MODEL,
        help=f"Modelo Ollama a usar (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt como argumento. Si se omite, se lee de stdin.",
    )
    args = parser.parse_args()

    if args.prompt:
        prompt = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        parser.print_help()
        sys.exit(1)

    if not prompt:
        print("[ollama_wrapper] Prompt vacío.", file=sys.stderr)
        sys.exit(1)

    sys.exit(stream_response(args.model, prompt))


if __name__ == "__main__":
    main()
