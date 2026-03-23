#!/usr/bin/env python3
"""
DQIII8 — Ollama Wrapper
Sends a prompt to Ollama and streams the response cleanly.

Usage:
    echo "write factorial in Python" | python3 bin/ollama_wrapper.py
    python3 bin/ollama_wrapper.py --model llama3 "explain what a closure is"
    python3 bin/ollama_wrapper.py "list of sorting algorithms"
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

OLLAMA_URL = "http://localhost:11434/api/generate"  # nosemgrep
DEFAULT_MODEL = "qwen2.5-coder:7b"

# Ollama runs locally — HTTP to localhost is intentional (no TLS support)
_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _validate_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith(f".{h}") for h in _ALLOWED_HOSTS):
        raise ValueError(f"URL not allowed: {url}")


def load_agent_system_prompt(agent_name: str) -> str:
    """Load agent MD from .claude/agents/{agent_name}.md, stripping YAML frontmatter."""
    if not agent_name or agent_name == "default":
        return ""
    jarvis = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
    md_path = jarvis / ".claude" / "agents" / f"{agent_name}.md"
    if not md_path.exists():
        return ""
    content = md_path.read_text(encoding="utf-8")
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip("\n")
    return content.strip()


def stream_response(model: str, prompt: str, system_prompt: str = "") -> int:
    _validate_url(OLLAMA_URL)
    body: dict = {"model": model, "prompt": prompt, "stream": True}
    if system_prompt:
        body["system"] = system_prompt
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # nosemgrep
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:  # nosemgrep
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
        print(f"[ollama_wrapper] Error connecting to Ollama: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sends a prompt to Ollama and streams the response."
    )
    parser.add_argument(
        "--model",
        "-m",
        default=DEFAULT_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--agent",
        "-a",
        default="",
        help="Agent name — loads .claude/agents/{agent}.md as system prompt",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt as argument. If omitted, reads from stdin.",
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
        print("[ollama_wrapper] Empty prompt.", file=sys.stderr)
        sys.exit(1)

    system_prompt = load_agent_system_prompt(args.agent)
    if system_prompt:
        print(f"[ollama_wrapper] system prompt loaded: {args.agent} ({len(system_prompt)} chars)", file=sys.stderr)

    sys.exit(stream_response(args.model, prompt, system_prompt))


if __name__ == "__main__":
    main()
