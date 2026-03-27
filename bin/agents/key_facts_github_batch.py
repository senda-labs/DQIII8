#!/usr/bin/env python3
"""
DQIII8 — Key Facts Generator (GitHub Models fallback)

One-shot batch to fill chunk_key_facts using GitHub Models (deepseek-v3-0324)
when Groq is rate-limited. Same DB schema, same output format.

Usage:
    python3 bin/agents/key_facts_github_batch.py
    python3 bin/agents/key_facts_github_batch.py --limit 500
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"

GH_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
GH_MODEL = "deepseek-v3-0324"
MAX_TOKENS = 256
CALL_DELAY_S = 0.5  # GitHub Models allows higher throughput

log = logging.getLogger(__name__)


def chunk_hash(text: str) -> str:
    return hashlib.sha256(text[:200].encode("utf-8")).hexdigest()


def _get_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        env_file = DQIII8_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return token


def _call_github(prompt: str, token: str) -> str | None:
    payload = json.dumps(
        {
            "model": GH_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "temperature": 0.0,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        GH_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 429:
            log.warning("GitHub Models rate-limited (429)")
            return "__RATE_LIMITED__"
        log.error("GitHub Models HTTP %s: %s", e.code, body[:120])
        return None
    except Exception as exc:
        log.error("GitHub Models request failed: %s", exc)
        return None


def _build_prompt(text: str, domain: str) -> str:
    return (
        f"Extract 3-5 key facts from this {domain.replace('_', ' ')} knowledge chunk. "
        "Return ONLY a JSON array of short strings (max 15 words each). "
        "No explanation, no markdown fences.\n\n"
        f"CHUNK:\n{text[:800]}"
    )


def _parse_facts(raw: str) -> list[str] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        result = json.loads(raw)
        if isinstance(result, list) and all(isinstance(f, str) for f in result):
            return [f.strip() for f in result if f.strip()]
    except json.JSONDecodeError:
        pass
    return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=0, help="Max chunks to process (0=all)"
    )
    args = parser.parse_args()

    token = _get_github_token()
    if not token:
        log.error("GITHUB_TOKEN not found")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    all_chunks = conn.execute(
        "SELECT id, domain, source, text FROM vector_chunks WHERE text IS NOT NULL AND text != ''"
    ).fetchall()
    cached = {
        r[0] for r in conn.execute("SELECT chunk_hash FROM chunk_key_facts").fetchall()
    }

    pending = [dict(c) for c in all_chunks if chunk_hash(c["text"]) not in cached]
    if args.limit > 0:
        pending = pending[: args.limit]

    print(
        f"[key_facts-gh] total={len(all_chunks)} cached={len(cached)} pending={len(pending)}"
    )
    if not pending:
        print("[key_facts-gh] Nothing to do.")
        conn.close()
        return

    ok = errors = 0
    for i, chunk in enumerate(pending, 1):
        ch = chunk_hash(chunk["text"])
        prompt = _build_prompt(chunk["text"], chunk.get("domain") or "general")
        raw = _call_github(prompt, token)

        if raw == "__RATE_LIMITED__":
            print(f"  [{i}/{len(pending)}] Rate-limited — stopping. ({ok} done)")
            break

        if raw is None:
            errors += 1
            continue

        facts = _parse_facts(raw)
        if not facts:
            log.warning("Parse fail chunk id=%s — raw: %s", chunk["id"], raw[:80])
            errors += 1
            continue

        conn.execute(
            "INSERT OR IGNORE INTO chunk_key_facts (chunk_hash, source, domain, key_facts, generated_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ch,
                chunk["source"],
                chunk.get("domain") or "",
                json.dumps(facts, ensure_ascii=False),
                GH_MODEL,
            ),
        )
        conn.commit()
        ok += 1

        if i % 25 == 0 or i == len(pending):
            print(f"  [{i}/{len(pending)}] ok={ok} err={errors}", flush=True)

        time.sleep(CALL_DELAY_S)

    conn.close()
    print(f"\n[key_facts-gh] Done — ok={ok} errors={errors}")


if __name__ == "__main__":
    main()
