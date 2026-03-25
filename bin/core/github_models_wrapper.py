#!/usr/bin/env python3
"""
DQIII8 — GitHub Models Wrapper
Endpoint: https://models.inference.ai.azure.com/chat/completions
Auth: Bearer GITHUB_TOKEN

Confirmed working models (2026-03-25):
  gpt-4o-mini          ~1400ms   OpenAI
  deepseek-r1          ~900ms    DeepSeek (includes <think> blocks)
  deepseek-v3-0324     ~340ms    DeepSeek — fastest
  llama-3.3-70b-instruct ~1000ms Meta
  codestral-2501       ~440ms    Mistral AI (code-optimized)

Rate limits (free tier): 20,000 req / 2,000,000 tokens per period

Usage:
  python3 github_models_wrapper.py --test [model]
  python3 github_models_wrapper.py --list
  python3 github_models_wrapper.py --model deepseek-v3-0324 "explain asyncio"
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
CATALOG_URL = "https://models.github.ai/catalog/models"

# Models confirmed working on DQIII8 (short IDs, no publisher prefix)
CONFIRMED_MODELS = {
    "gpt-4o-mini": {
        "publisher": "OpenAI",
        "latency_ms": 1400,
        "notes": "reliable general",
    },
    "deepseek-r1": {
        "publisher": "DeepSeek",
        "latency_ms": 900,
        "notes": "reasoning, includes <think>",
    },
    "deepseek-v3-0324": {
        "publisher": "DeepSeek",
        "latency_ms": 340,
        "notes": "fastest, strong general",
    },
    "llama-3.3-70b-instruct": {
        "publisher": "Meta",
        "latency_ms": 1000,
        "notes": "same as Groq tier-B",
    },
    "codestral-2501": {
        "publisher": "Mistral AI",
        "latency_ms": 440,
        "notes": "code-optimized",
    },
}
DEFAULT_TEST_MODEL = "deepseek-v3-0324"


def _get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        env_file = Path(__file__).parent.parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return token


def call_github_model(
    model: str,
    messages: list[dict],
    system_prompt: str | None = None,
    max_tokens: int = 1000,
    timeout: int = 30,
) -> str | None:
    token = _get_token()
    if not token:
        log.error("GITHUB_TOKEN not found in env or .env file")
        return None

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    payload = json.dumps(
        {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body).get("error", {})
            code = err.get("code", e.code)
            msg = err.get("message", "")[:120]
        except Exception:
            code, msg = e.code, body[:120]
        if code == 429 or e.code == 429:
            log.warning("GitHub Models rate limited (429) — model=%s", model)
        elif e.code in (401, 403):
            log.error("GitHub Models auth failed (%s) — check GITHUB_TOKEN", e.code)
        else:
            log.error("GitHub Models HTTP %s (%s): %s", e.code, code, msg)
        return None
    except Exception as e:
        log.error("GitHub Models request failed: %s", e)
        return None


def cmd_test(model: str) -> None:
    print(f"Testing {model} ...")
    t0 = time.monotonic()
    result = call_github_model(
        model=model,
        messages=[{"role": "user", "content": "What is 2+2? Answer only the number."}],
        max_tokens=50,
    )
    ms = int((time.monotonic() - t0) * 1000)
    if result is not None:
        print(f"  OK ({ms}ms): {result.strip()[:100]}")
    else:
        print(f"  FAILED ({ms}ms) — check logs")


def cmd_list() -> None:
    print("GitHub Models — confirmed working on DQIII8:\n")
    print(f"  {'Model':<30} {'Publisher':<12} {'Latency':>9}  Notes")
    print("  " + "-" * 70)
    for mid, info in CONFIRMED_MODELS.items():
        print(
            f"  {mid:<30} {info['publisher']:<12} {info['latency_ms']:>7}ms  {info['notes']}"
        )
    print(f"\nEndpoint: {ENDPOINT}")
    print("Rate limit: 20,000 req / 2,000,000 tokens per period")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="GitHub Models wrapper for DQIII8")
    parser.add_argument("--model", default=DEFAULT_TEST_MODEL, help="Model ID")
    parser.add_argument("--test", action="store_true", help="Run smoke test")
    parser.add_argument(
        "--list", action="store_true", dest="list_models", help="List confirmed models"
    )
    parser.add_argument("prompt", nargs="?", help="Prompt to send")
    args = parser.parse_args()

    if args.list_models:
        cmd_list()
        return

    if args.test:
        cmd_test(args.model)
        return

    if args.prompt:
        result = call_github_model(
            model=args.model,
            messages=[{"role": "user", "content": args.prompt}],
        )
        if result:
            print(result)
        else:
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
