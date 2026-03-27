#!/usr/bin/env python3
"""
DQIII8 — Chunk Freshness Reviewer

Evaluates knowledge base chunk quality on 3 dimensions:
1. Redundancy: Does the LLM already know this without the chunk?
2. Freshness: Does the chunk contain temporal data that could be outdated?
3. Usage: Has the chunk been accessed in queries recently?

Results stored in chunk_health table for Enricher v4 to penalize low-value chunks.

Usage:
    python3 bin/agents/chunk_freshness_reviewer.py --dry-run
    python3 bin/agents/chunk_freshness_reviewer.py --review 10
    python3 bin/agents/chunk_freshness_reviewer.py --report
    python3 bin/agents/chunk_freshness_reviewer.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
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

log = logging.getLogger("freshness_reviewer")

CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS chunk_health (
    chunk_id    INTEGER PRIMARY KEY,
    domain      TEXT    DEFAULT '',
    redundancy_score REAL DEFAULT 0.5,
    freshness   TEXT    DEFAULT 'unknown',
    usage_30d   INTEGER DEFAULT 0,
    verdict     TEXT    DEFAULT 'keep',
    reviewed_at TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (chunk_id) REFERENCES vector_chunks(id)
)"""


# ── Groq multi-key LLM caller (same pattern as key_facts_multikey_batch) ─────


def _load_groq_keys() -> list[str]:
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


def _call_groq(prompt: str, token: str, max_tokens: int = 200) -> str | None:
    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
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
            "User-Agent": "Mozilla/5.0 (compatible; DQIII8-freshness/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "__RATE_LIMITED__"
        log.error("Groq HTTP %s", e.code)
        return None
    except Exception as exc:
        log.error("Groq call failed: %s", exc)
        return None


class GroqCaller:
    """Round-robin Groq caller with automatic key rotation on rate limit."""

    def __init__(self) -> None:
        self.keys = _load_groq_keys()
        self.idx = 0
        self.exhausted: set[int] = set()

    def call(self, prompt: str, max_tokens: int = 200) -> str | None:
        if not self.keys:
            log.error("No Groq keys loaded")
            return None

        attempts = len(self.keys)
        for _ in range(attempts):
            if len(self.exhausted) >= len(self.keys):
                log.warning("All %d Groq keys exhausted", len(self.keys))
                return None

            while self.idx in self.exhausted:
                self.idx = (self.idx + 1) % len(self.keys)

            result = _call_groq(prompt, self.keys[self.idx], max_tokens)
            if result == "__RATE_LIMITED__":
                self.exhausted.add(self.idx)
                remaining = len(self.keys) - len(self.exhausted)
                log.info("Key #%d rate-limited, %d remaining", self.idx + 1, remaining)
                self.idx = (self.idx + 1) % len(self.keys)
                continue
            return result

        return None


# ── Assessment functions ─────────────────────────────────────────────────────


def _has_temporal_data(text: str) -> bool:
    """Check if chunk contains data that could become outdated."""
    patterns = [
        r"\b20[12]\d\b",
        r"\b\d+(?:\.\d+)?%",
        r"\b(?:GDP|PIB|inflation|unemployment)\b",
        r"\b(?:currently|as of|recent|latest)\b",
        r"\b(?:million|billion|trillion)\b.*\b(?:dollar|euro|pound)\b",
        r"\b(?:ranked?|ranking)\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _assess_redundancy(text: str, caller: GroqCaller) -> float:
    """Test if the LLM already knows this information without the chunk.

    Method: generate a question from the chunk, ask the LLM without context,
    compare key term overlap between chunk and answer.

    Returns: 0.0 (unique info) to 1.0 (fully redundant)
    """
    # Step 1: Generate question from chunk
    question = caller.call(
        "Genera UNA pregunta concreta que este texto responde. "
        f"Solo la pregunta, nada más.\n\n{text[:300]}",
        max_tokens=80,
    )
    if not question or len(question.strip()) < 10:
        return 0.5

    # Step 2: Ask LLM WITHOUT the chunk
    answer = caller.call(f"Responde brevemente: {question.strip()}", max_tokens=150)
    if not answer:
        return 0.5

    # Step 3: Compare key terms (4+ chars, significant words)
    chunk_words = set(w.lower() for w in re.findall(r"\b\w{4,}\b", text))
    answer_words = set(w.lower() for w in re.findall(r"\b\w{4,}\b", answer))

    if not chunk_words:
        return 0.5

    overlap = len(chunk_words & answer_words) / len(chunk_words)
    return round(min(overlap * 1.5, 1.0), 2)


def _get_usage_30d(conn: sqlite3.Connection, text: str) -> int:
    """Get usage count in last 30 days via chunk_text_hash (MD5 of text[:100])."""
    text_hash = hashlib.md5(text[:100].encode()).hexdigest()[:16]
    row = conn.execute(
        "SELECT COUNT(*) FROM knowledge_usage "
        "WHERE chunk_text_hash = ? AND timestamp > datetime('now', '-30 days')",
        (text_hash,),
    ).fetchone()
    return row[0] if row else 0


def _verdict(redundancy: float, freshness: str, usage: int) -> str:
    """Determine chunk verdict based on 3 dimensions."""
    if redundancy >= 0.85 and freshness == "stale" and usage == 0:
        return "archive"
    if redundancy >= 0.80:
        return "demote"
    if freshness == "stale" and usage == 0:
        return "demote"
    return "keep"


# ── Commands ─────────────────────────────────────────────────────────────────


def cmd_review(conn: sqlite3.Connection, limit: int, dry_run: bool = False) -> dict:
    """Review unreviewed chunks."""
    pending = conn.execute(
        """SELECT vc.id, vc.domain, vc.text
           FROM vector_chunks vc
           LEFT JOIN chunk_health ch ON ch.chunk_id = vc.id
           WHERE ch.chunk_id IS NULL AND vc.text IS NOT NULL AND vc.text != ''
           ORDER BY vc.id
           LIMIT ?""",
        (limit,),
    ).fetchall()

    total_unreviewed = conn.execute(
        """SELECT COUNT(*) FROM vector_chunks vc
           LEFT JOIN chunk_health ch ON ch.chunk_id = vc.id
           WHERE ch.chunk_id IS NULL AND vc.text IS NOT NULL AND vc.text != ''"""
    ).fetchone()[0]

    if dry_run:
        print(
            f"[freshness] Would review {min(limit, total_unreviewed)} of {total_unreviewed} unreviewed chunks"
        )
        return {"pending": total_unreviewed}

    if not pending:
        print("[freshness] All chunks already reviewed.")
        return {"pending": 0}

    caller = GroqCaller()
    if not caller.keys:
        print("[freshness] ERROR: No Groq API keys found")
        return {"errors": 1}

    print(
        f"[freshness] Reviewing {len(pending)} chunks ({len(caller.keys)} Groq keys loaded)"
    )

    stats: dict[str, int] = {"keep": 0, "demote": 0, "archive": 0, "errors": 0}

    for i, (chunk_id, domain, text) in enumerate(pending, 1):
        if caller.exhausted and len(caller.exhausted) >= len(caller.keys):
            print(
                f"  [{i}/{len(pending)}] All keys exhausted — stopping. ({sum(v for k,v in stats.items() if k != 'errors')} done)"
            )
            break

        redundancy = _assess_redundancy(text, caller)
        freshness = "stale" if _has_temporal_data(text) else "fresh"
        usage = _get_usage_30d(conn, text)
        v = _verdict(redundancy, freshness, usage)

        conn.execute(
            """INSERT OR REPLACE INTO chunk_health
               (chunk_id, domain, redundancy_score, freshness, usage_30d, verdict, reviewed_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (chunk_id, domain or "", redundancy, freshness, usage, v),
        )
        stats[v] = stats.get(v, 0) + 1

        if i % 5 == 0 or i == len(pending):
            print(
                f"  [{i}/{len(pending)}] keep={stats['keep']} demote={stats['demote']} "
                f"archive={stats['archive']} err={stats['errors']}",
                flush=True,
            )

        time.sleep(1.5)  # Rate limit spacing (2 LLM calls per chunk)

    conn.commit()
    return stats


def cmd_report(conn: sqlite3.Connection) -> None:
    """Print health summary."""
    total = conn.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE text IS NOT NULL AND text != ''"
    ).fetchone()[0]

    try:
        reviewed = conn.execute("SELECT COUNT(*) FROM chunk_health").fetchone()[0]
    except sqlite3.OperationalError:
        print("[freshness] chunk_health table does not exist yet. Run --review first.")
        return

    print(f"\n{'=' * 55}")
    print(f"  Chunk Health Report — {reviewed}/{total} reviewed")
    print(f"{'=' * 55}")

    rows = conn.execute(
        """SELECT verdict, COUNT(*), ROUND(AVG(redundancy_score), 2), SUM(usage_30d)
           FROM chunk_health GROUP BY verdict ORDER BY COUNT(*) DESC"""
    ).fetchall()

    for verdict, count, avg_r, total_usage in rows:
        print(
            f"  {verdict:8s}: {count:4d} chunks  (avg_redundancy={avg_r}, usage_30d={total_usage or 0})"
        )

    print(f"\n  By domain:")
    domain_rows = conn.execute(
        """SELECT COALESCE(NULLIF(domain, ''), '(blank)') as d, verdict, COUNT(*)
           FROM chunk_health GROUP BY d, verdict ORDER BY d, verdict"""
    ).fetchall()
    for domain, verdict, count in domain_rows:
        print(f"    {domain:20s} {verdict:8s}: {count}")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Chunk Freshness Reviewer")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--review", type=int, default=0, metavar="N", help="Review N unreviewed chunks"
    )
    group.add_argument(
        "--all", action="store_true", help="Review all unreviewed chunks"
    )
    group.add_argument("--report", action="store_true", help="Show health summary")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be reviewed"
    )
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(CREATE_TABLE)
    conn.commit()

    if args.report:
        cmd_report(conn)
    elif args.dry_run:
        cmd_review(conn, limit=args.review or 9999, dry_run=True)
    elif args.all:
        stats = cmd_review(conn, limit=9999)
        print(f"\nDone: {stats}")
        cmd_report(conn)
    elif args.review > 0:
        stats = cmd_review(conn, limit=args.review)
        print(f"\nDone: {stats}")
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
