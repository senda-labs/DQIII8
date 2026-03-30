#!/usr/bin/env python3
"""
summarize_output.py — Haiku/Llama3 summarizer para outputs grandes.

Cuando un output fue truncado, este script envía el texto completo
a un modelo ultrabarato (OpenRouter free / Groq) con una pregunta
específica y devuelve ≤200 tokens al modelo principal.

Uso:
  # Modo pipe (recibe el output grande por stdin)
  cat app.log | python3 bin/tools/summarize_output.py --query "¿Qué error aparece?"

  # Modo archivo
  python3 bin/tools/summarize_output.py --file /tmp/big_output.txt --query "¿Cuál es el traceback?"

  # Con texto directo
  python3 bin/tools/summarize_output.py --text "..." --query "resume en 3 bullets"

Retorna: respuesta de ≤200 tokens + metadata de coste/modelo usado.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
_HOOKS_DIR = DQIII8_ROOT / ".claude" / "hooks"
_ENV_PATH = DQIII8_ROOT / ".env"

MAX_INPUT_CHARS = 8_000   # ~2k tokens of input to the cheap model
MAX_OUTPUT_TOKENS = 200


def _load_env_key(name: str) -> str:
    if not _ENV_PATH.exists():
        return os.environ.get(name, "")
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        if k.strip() == name:
            return v.strip().strip("\"'")
    return os.environ.get(name, "")


async def _call_openrouter(text: str, query: str) -> tuple[str, str]:
    """Call OpenRouter free tier (meta-llama/llama-3.3-70b-instruct:free)."""
    import httpx  # lightweight, available on system

    api_key = _load_env_key("OPENROUTER_API_KEY")
    if not api_key:
        return "", "no_openrouter_key"

    prompt = (
        f"Analyze the following output and answer ONLY this question in ≤200 tokens: {query}\n\n"
        f"OUTPUT:\n{text[:MAX_INPUT_CHARS]}"
    )

    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_OUTPUT_TOKENS,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        r.raise_for_status()
        data = r.json()
        answer = data["choices"][0]["message"]["content"].strip()
        model = data.get("model", "openrouter-free")
        return answer, model
    except Exception as e:
        return "", f"openrouter_error:{e}"


async def _call_groq(text: str, query: str) -> tuple[str, str]:
    """Fallback to Groq free tier."""
    import httpx

    # Try primary Groq key first
    api_key = _load_env_key("GROQ_API_KEY")
    if not api_key:
        return "", "no_groq_key"

    prompt = (
        f"Answer ONLY this question in ≤200 tokens: {query}\n\nOUTPUT:\n{text[:MAX_INPUT_CHARS]}"
    )

    payload = {
        "model": "llama-3.1-8b-instant",  # fastest + cheapest Groq model
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_OUTPUT_TOKENS,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        r.raise_for_status()
        data = r.json()
        answer = data["choices"][0]["message"]["content"].strip()
        return answer, "groq/llama-3.1-8b-instant"
    except Exception as e:
        return "", f"groq_error:{e}"


async def _summarize(text: str, query: str) -> None:
    """Try OpenRouter first, fallback to Groq."""
    char_count = len(text)
    token_est = round(char_count / 4)

    print(f"[summarize_output] Input: {char_count:,} chars (~{token_est:,} tokens)", file=sys.stderr)
    print(f"[summarize_output] Query: {query}", file=sys.stderr)

    answer, model = await _call_openrouter(text, query)
    if not answer:
        print(f"[summarize_output] OpenRouter failed ({model}), trying Groq...", file=sys.stderr)
        answer, model = await _call_groq(text, query)

    if not answer:
        print(f"[summarize_output] All models failed. Last error: {model}", file=sys.stderr)
        sys.exit(1)

    print(f"\n[SUMMARY via {model}]\n{answer}\n[END SUMMARY — ≤{MAX_OUTPUT_TOKENS} tokens]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize large output using cheap LLM")
    parser.add_argument("--query", "-q", required=True,
                        help="The specific question to answer about the output")
    parser.add_argument("--text", "-t", default="",
                        help="Text to analyze (if not using stdin or --file)")
    parser.add_argument("--file", "-f", default="",
                        help="Path to file containing the output to analyze")
    args = parser.parse_args()

    # ── Determine input text ──────────────────────────────────────────────────
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    else:
        print("Error: provide --text, --file, or pipe input via stdin", file=sys.stderr)
        sys.exit(1)

    if not text.strip():
        print("Error: input text is empty", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_summarize(text, args.query))


if __name__ == "__main__":
    main()
