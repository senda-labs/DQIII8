#!/usr/bin/env python3
"""
DQIII8 — Key Facts Generator

Extracts key facts from vector_chunks using Groq llama-3.3-70b and caches
them in chunk_key_facts (keyed by SHA256(text[:200])).

Usage:
    python3 bin/agents/key_facts_generator.py --domain applied_sciences
    python3 bin/agents/key_facts_generator.py --all
    python3 bin/agents/key_facts_generator.py --report
    python3 bin/agents/key_facts_generator.py --all --dry-run

Rate limits: Groq free tier — 100K tokens/day. Script skips on 429 and logs
the position so the next run resumes from uncached chunks automatically.
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

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS_PER_CALL = 256
CALL_DELAY_S = 2.0  # conservative — Groq free tier has burst limits

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def chunk_hash(text: str) -> str:
    """SHA256 of first 200 chars — stable cache key."""
    return hashlib.sha256(text[:200].encode("utf-8")).hexdigest()


def _get_groq_token() -> str:
    token = os.environ.get("GROQ_API_KEY", "")
    if not token:
        env_file = DQIII8_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GROQ_API_KEY="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return token


def _call_groq(prompt: str, token: str) -> str | None:
    """Call Groq; return content string or None (logs on error)."""
    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS_PER_CALL,
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
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body).get("error", {})
            code = err.get("code", e.code)
            msg = err.get("message", "")[:120]
        except Exception:
            code, msg = e.code, body[:120]
        if e.code == 429:
            log.warning(
                "Groq rate-limited (429) — stopping batch. code=%s msg=%s", code, msg
            )
            return "__RATE_LIMITED__"
        log.error("Groq HTTP %s (%s): %s", e.code, code, msg)
        return None
    except Exception as exc:
        log.error("Groq request failed: %s", exc)
        return None


def _build_extraction_prompt(text: str, domain: str) -> str:
    return (
        f"Extract 3-5 key facts from this {domain.replace('_', ' ')} knowledge chunk. "
        "Return ONLY a JSON array of short strings (max 15 words each). "
        "No explanation, no markdown fences.\n\n"
        f"CHUNK:\n{text[:800]}"
    )


def _parse_facts(raw: str) -> list[str] | None:
    """Parse JSON array from model output. Returns None on failure."""
    raw = raw.strip()
    # Strip markdown fences if present
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


# ── DB helpers ────────────────────────────────────────────────────────────────


def _load_chunks(domain: str | None) -> list[dict]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if domain:
        rows = conn.execute(
            "SELECT id, domain, source, text FROM vector_chunks WHERE domain = ? AND text IS NOT NULL AND text != ''",
            (domain,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, domain, source, text FROM vector_chunks WHERE text IS NOT NULL AND text != ''"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_cached_hashes() -> set[str]:
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT chunk_hash FROM chunk_key_facts").fetchall()
    conn.close()
    return {r[0] for r in rows}


def _save_facts(ch: str, source: str, domain: str, facts: list[str]) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT OR IGNORE INTO chunk_key_facts (chunk_hash, source, domain, key_facts, generated_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (ch, source, domain or "", json.dumps(facts, ensure_ascii=False), GROQ_MODEL),
    )
    conn.commit()
    conn.close()


# ── Commands ──────────────────────────────────────────────────────────────────


def cmd_report() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    total_chunks = conn.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE text IS NOT NULL AND text != ''"
    ).fetchone()[0]
    cached = conn.execute("SELECT COUNT(*) FROM chunk_key_facts").fetchone()[0]
    by_domain = conn.execute(
        "SELECT domain, COUNT(*) FROM chunk_key_facts GROUP BY domain ORDER BY COUNT(*) DESC"
    ).fetchall()
    conn.close()

    print(f"\n=== Key Facts Cache Report ===")
    print(f"Total chunks : {total_chunks}")
    print(f"Cached       : {cached}  ({cached / max(total_chunks, 1) * 100:.1f}%)")
    print(f"Remaining    : {total_chunks - cached}\n")
    print(f"  {'Domain':<25} {'Cached':>8}")
    print("  " + "-" * 35)
    for domain, cnt in by_domain:
        print(f"  {(domain or '(blank)'):<25} {cnt:>8}")
    print()


def cmd_generate(domain: str | None, dry_run: bool) -> None:
    token = _get_groq_token()
    if not token:
        log.error("GROQ_API_KEY not found — cannot generate facts.")
        sys.exit(1)

    chunks = _load_chunks(domain)
    cached = _load_cached_hashes()

    pending = [c for c in chunks if chunk_hash(c["text"]) not in cached]
    label = domain or "ALL"
    print(
        f"\n[key_facts] domain={label}  chunks={len(chunks)}  cached={len(cached)}  pending={len(pending)}"
    )
    if not pending:
        print("[key_facts] Nothing to do.")
        return

    if dry_run:
        print(f"[key_facts] --dry-run: would process {len(pending)} chunks.")
        return

    ok = skipped = errors = 0
    for i, chunk in enumerate(pending, 1):
        ch = chunk_hash(chunk["text"])
        prompt = _build_extraction_prompt(
            chunk["text"], chunk.get("domain") or "general"
        )
        raw = _call_groq(prompt, token)

        if raw == "__RATE_LIMITED__":
            print(
                f"  [{i}/{len(pending)}] Rate-limited — stopping. ({ok} done, {skipped} skipped)"
            )
            break

        if raw is None:
            errors += 1
            log.warning("Skipping chunk id=%s (call failed)", chunk["id"])
            continue

        facts = _parse_facts(raw)
        if not facts:
            log.warning(
                "Could not parse facts for chunk id=%s — raw: %s", chunk["id"], raw[:80]
            )
            errors += 1
            continue

        _save_facts(ch, chunk["source"], chunk.get("domain") or "", facts)
        ok += 1
        if i % 10 == 0 or i == len(pending):
            print(f"  [{i}/{len(pending)}] ok={ok} skip={skipped} err={errors}")

        time.sleep(CALL_DELAY_S)

    print(f"\n[key_facts] Done — ok={ok} skipped={skipped} errors={errors}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Extract and cache key facts from knowledge chunks"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--domain", help="Process one domain (e.g. applied_sciences)")
    group.add_argument("--all", action="store_true", help="Process all domains")
    group.add_argument(
        "--report", action="store_true", help="Show cache status (no API calls)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Count pending without calling API"
    )
    args = parser.parse_args()

    if args.report:
        cmd_report()
        return

    if args.all:
        cmd_generate(domain=None, dry_run=args.dry_run)
        return

    if args.domain:
        cmd_generate(domain=args.domain, dry_run=args.dry_run)
        return

    # Default: report
    cmd_report()


if __name__ == "__main__":
    main()
