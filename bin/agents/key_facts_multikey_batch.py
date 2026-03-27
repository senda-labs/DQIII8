#!/usr/bin/env python3
"""
DQIII8 — Key Facts Generator (multi-key Groq rotation)

Rotates through 6 Groq API keys to maximize throughput when individual
keys hit rate limits. Same DB schema as key_facts_generator.py.

Usage:
    python3 bin/agents/key_facts_multikey_batch.py
    python3 bin/agents/key_facts_multikey_batch.py --limit 500
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
ENV_FILE = DQIII8_ROOT / "my-projects" / "auto-report" / ".env"

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 256
CALL_DELAY_S = 1.5

log = logging.getLogger(__name__)


def chunk_hash(text: str) -> str:
    return hashlib.sha256(text[:200].encode("utf-8")).hexdigest()


def _load_groq_keys() -> list[str]:
    """Load all GROQ_API_KEY variants from the env file."""
    keys: list[str] = []
    suffixes = [
        "",
        "_FALLBACK",
        "_FALLBACK_2",
        "_FALLBACK_3",
        "_FALLBACK_4",
        "_FALLBACK_5",
    ]
    if not ENV_FILE.exists():
        log.error("Env file not found: %s", ENV_FILE)
        return keys
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for suffix in suffixes:
        target = f"GROQ_API_KEY{suffix}="
        for line in lines:
            if line.startswith(target):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    keys.append(val)
                break
    return keys


def _call_groq(prompt: str, token: str) -> str | None:
    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "temperature": 0.0,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        GROQ_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; DQIII8-keyfacts/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "__RATE_LIMITED__"
        body = e.read().decode("utf-8", errors="replace")[:120]
        log.error("Groq HTTP %s: %s", e.code, body)
        return None
    except Exception as exc:
        log.error("Groq request failed: %s", exc)
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max chunks (0=all)")
    args = parser.parse_args()

    keys = _load_groq_keys()
    if not keys:
        log.error("No Groq keys found in %s", ENV_FILE)
        sys.exit(1)
    print(f"[key_facts-multi] Loaded {len(keys)} Groq API keys")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    all_chunks = conn.execute(
        "SELECT id, domain, source, text FROM vector_chunks "
        "WHERE text IS NOT NULL AND text != ''"
    ).fetchall()
    cached = {
        r[0] for r in conn.execute("SELECT chunk_hash FROM chunk_key_facts").fetchall()
    }

    pending = [dict(c) for c in all_chunks if chunk_hash(c["text"]) not in cached]
    if args.limit > 0:
        pending = pending[: args.limit]

    print(
        f"[key_facts-multi] total={len(all_chunks)} cached={len(cached)} pending={len(pending)}"
    )
    if not pending:
        print("[key_facts-multi] Nothing to do.")
        conn.close()
        return

    ok = errors = 0
    key_idx = 0
    exhausted_keys: set[int] = set()

    for i, chunk in enumerate(pending, 1):
        # All keys exhausted?
        if len(exhausted_keys) >= len(keys):
            print(
                f"  [{i}/{len(pending)}] All {len(keys)} keys exhausted — stopping. ({ok} done)"
            )
            break

        # Skip to next available key
        while key_idx in exhausted_keys:
            key_idx = (key_idx + 1) % len(keys)

        ch = chunk_hash(chunk["text"])
        prompt = _build_prompt(chunk["text"], chunk.get("domain") or "general")
        raw = _call_groq(prompt, keys[key_idx])

        if raw == "__RATE_LIMITED__":
            exhausted_keys.add(key_idx)
            remaining = len(keys) - len(exhausted_keys)
            print(
                f"  [{i}/{len(pending)}] Key #{key_idx + 1} rate-limited. "
                f"{remaining} keys remaining. ({ok} done so far)"
            )
            if remaining == 0:
                print(f"  All keys exhausted — stopping.")
                break
            key_idx = (key_idx + 1) % len(keys)
            # Retry this chunk with next key
            raw = _call_groq(prompt, keys[key_idx])
            if raw == "__RATE_LIMITED__":
                exhausted_keys.add(key_idx)
                # Try remaining keys for this chunk
                retried = False
                for k in range(len(keys)):
                    if k not in exhausted_keys:
                        raw = _call_groq(prompt, keys[k])
                        if raw != "__RATE_LIMITED__":
                            key_idx = k
                            retried = True
                            break
                        exhausted_keys.add(k)
                if not retried:
                    print(f"  All keys exhausted — stopping. ({ok} done)")
                    break

        if raw is None or raw == "__RATE_LIMITED__":
            errors += 1
            continue

        facts = _parse_facts(raw)
        if not facts:
            log.warning("Parse fail chunk id=%s — raw: %s", chunk["id"], raw[:80])
            errors += 1
            continue

        conn.execute(
            "INSERT OR IGNORE INTO chunk_key_facts "
            "(chunk_hash, source, domain, key_facts, generated_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ch,
                chunk["source"],
                chunk.get("domain") or "",
                json.dumps(facts, ensure_ascii=False),
                GROQ_MODEL,
            ),
        )
        conn.commit()
        ok += 1

        if i % 25 == 0 or i == len(pending):
            print(
                f"  [{i}/{len(pending)}] ok={ok} err={errors} key=#{key_idx + 1}",
                flush=True,
            )

        time.sleep(CALL_DELAY_S)

    conn.close()
    final_cached = (
        sqlite3.connect(str(DB_PATH))
        .execute("SELECT COUNT(*) FROM chunk_key_facts")
        .fetchone()[0]
    )
    print(
        f"\n[key_facts-multi] Done — ok={ok} errors={errors} total_cached={final_cached}/1309"
    )


if __name__ == "__main__":
    main()
