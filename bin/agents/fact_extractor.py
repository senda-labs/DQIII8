#!/usr/bin/env python3
"""
DQIII8 — Fact Extractor  (Bloque 9 Fase 4)

Extracts entity-predicate-value triples from free text using an LLM,
then stores them in the temporal facts store via temporal_memory.add_fact().

Public API:
    extract_facts(text, domain=None)   → list[dict]   (each: entity, predicate, value)
    store_facts(triples, domain, session_id) → int    (count stored)

CLI:
    python3 bin/agents/fact_extractor.py --text "Python 3.12 was released in 2023"
    python3 bin/agents/fact_extractor.py --batch [--hours N] [--domain DOMAIN]
    python3 bin/agents/fact_extractor.py --demo
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))

log = logging.getLogger(__name__)

# ── LLM prompt ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a fact extraction system. "
    "Extract only verified, objective factual statements from the given text. "
    "No opinions. No speculation. No questions. "
    "Respond ONLY with a valid JSON array of objects, each with keys: "
    '"entity" (subject), "predicate" (relationship/property), "value" (object/value). '
    "Maximum 5 facts. If no clear facts exist, respond with []."
)

_USER_TEMPLATE = "Extract factual statements from this text:\n\n{text}"

# ── Core extraction ───────────────────────────────────────────────────────────


def extract_facts(text: str, domain: Optional[str] = None) -> list[dict]:
    """
    Call LLM (Groq llama-3.3-70b via openrouter_wrapper) to extract fact triples.
    Returns list of dicts with keys: entity, predicate, value.
    Returns [] on any failure (parse error, LLM unavailable, etc.).
    """
    text = text.strip()
    if not text or len(text) < 20:
        return []

    # Truncate to avoid token waste (LLM only needs enough context for 5 facts)
    if len(text) > 2000:
        text = text[:2000] + "…"

    try:
        from openrouter_wrapper import stream_response

        user_prompt = _USER_TEMPLATE.format(text=text)
        full_prompt = f"{_SYSTEM_PROMPT}\n\n{user_prompt}"

        # Use Groq / llama-3.3-70b (Tier B — balanced cost/quality)
        response_text, _, _, ok = stream_response(
            provider_name="groq",
            model="llama-3.3-70b-versatile",
            prompt=full_prompt,
            system_prompt=_SYSTEM_PROMPT,
        )

        if not ok or not response_text:
            log.warning("[fact_extractor] LLM call failed or empty response")
            return []

        return _parse_triples(response_text)

    except Exception as exc:
        log.warning("[fact_extractor] extract_facts failed: %s", exc)
        return []


def _parse_triples(response: str) -> list[dict]:
    """
    Parse LLM response into a list of (entity, predicate, value) dicts.
    Handles both bare JSON and JSON wrapped in code fences.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()

    # Find first '[' to skip any preamble text
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        log.debug("[fact_extractor] no JSON array in response: %r", cleaned[:200])
        return []

    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        log.debug("[fact_extractor] JSON parse error: %s — raw: %r", exc, cleaned[:200])
        return []

    if not isinstance(data, list):
        return []

    triples = []
    for item in data[:5]:  # hard cap at 5
        if not isinstance(item, dict):
            continue
        entity = str(item.get("entity", "")).strip()
        predicate = str(item.get("predicate", "")).strip()
        value = str(item.get("value", "")).strip()
        if entity and predicate and value:
            triples.append({"entity": entity, "predicate": predicate, "value": value})

    return triples


# ── Storage ───────────────────────────────────────────────────────────────────


def store_facts(
    triples: list[dict],
    domain: str = "",
    session_id: Optional[str] = None,
    confidence: float = 0.85,
) -> int:
    """
    Store extracted triples in temporal_memory.
    Returns count of successfully stored facts.
    """
    if not triples:
        return 0

    try:
        from temporal_memory import add_episode, add_fact

        ep = add_episode(
            session_id or "fact_extractor",
            agent_name="fact_extractor",
            summary=f"Auto-extracted {len(triples)} facts",
            domain=domain,
        )
        stored = 0
        for t in triples:
            try:
                add_fact(
                    entity=t["entity"],
                    predicate=t["predicate"],
                    value=t["value"],
                    domain=domain,
                    source_episode_id=ep,
                    confidence=confidence,
                )
                stored += 1
            except Exception as exc:
                log.warning("[fact_extractor] store_fact failed: %s", exc)
        return stored
    except Exception as exc:
        log.warning("[fact_extractor] store_facts failed: %s", exc)
        return 0


# ── Batch mode ────────────────────────────────────────────────────────────────


def _get_recent_file_contents(hours: int = 4) -> list[tuple[str, str]]:
    """
    Query agent_actions for recently written markdown/text files,
    read their content, return list of (domain, content) tuples.
    Falls back to [] if DB or files unavailable.
    """
    db_path = DQIII8_ROOT / "database" / "dqiii8.db"
    if not db_path.exists():
        return []

    results = []
    try:
        conn = sqlite3.connect(str(db_path), timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT DISTINCT file_path, domain
            FROM agent_actions
            WHERE success = 1
              AND duration_ms > 10000
              AND file_path IS NOT NULL
              AND (file_path LIKE '%.md' OR file_path LIKE '%.txt')
              AND datetime(timestamp) >= datetime('now', ? || ' hours')
            ORDER BY timestamp DESC
            LIMIT 20
            """,
            (f"-{hours}",),
        ).fetchall()
        conn.close()

        for row in rows:
            path_str = row["file_path"]
            domain = row["domain"] or ""
            try:
                p = Path(path_str)
                if not p.is_absolute():
                    p = DQIII8_ROOT / path_str
                if p.exists() and p.stat().st_size < 50_000:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if len(content.strip()) >= 50:
                        results.append((domain, content))
            except Exception:
                pass

    except Exception as exc:
        log.warning("[fact_extractor] batch DB query failed: %s", exc)

    return results


def run_batch(
    hours: int = 4, domain: Optional[str] = None, dry_run: bool = False
) -> dict:
    """
    Batch extraction from recent session activity.
    Returns stats dict: {files_checked, total_extracted, total_stored}.
    """
    texts = _get_recent_file_contents(hours)
    total_extracted = 0
    total_stored = 0

    for file_domain, content in texts:
        effective_domain = domain or file_domain or ""
        triples = extract_facts(content, domain=effective_domain)
        total_extracted += len(triples)

        if triples and not dry_run:
            n = store_facts(triples, domain=effective_domain)
            total_stored += n
            log.info(
                "[fact_extractor] stored %d/%d facts (domain=%s)",
                n,
                len(triples),
                effective_domain,
            )

    stats = {
        "files_checked": len(texts),
        "total_extracted": total_extracted,
        "total_stored": total_stored,
    }
    log.info("[fact_extractor] batch complete: %s", stats)
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="DQIII8 Fact Extractor")
    parser.add_argument("--text", metavar="TEXT", help="Extract facts from TEXT")
    parser.add_argument(
        "--batch", action="store_true", help="Batch from recent agent_actions"
    )
    parser.add_argument(
        "--hours", type=int, default=4, help="Hours back for --batch (default 4)"
    )
    parser.add_argument("--domain", default=None, help="Domain tag for extracted facts")
    parser.add_argument(
        "--dry-run", action="store_true", help="Extract but don't store"
    )
    parser.add_argument("--demo", action="store_true", help="Run demo extraction")
    args = parser.parse_args()

    if args.demo:
        sample = (
            "Python 3.12 was released in October 2023. "
            "It includes a new type parameter syntax. "
            "The WACC formula combines cost of equity and cost of debt. "
            "Kelly criterion maximizes long-term growth rate."
        )
        print(f"Input: {sample[:80]}…")
        triples = extract_facts(sample, domain=args.domain or "")
        print(f"Extracted {len(triples)} facts:")
        for t in triples:
            print(f"  ({t['entity']}, {t['predicate']}, {t['value']})")
        if triples and not args.dry_run:
            n = store_facts(triples, domain=args.domain or "demo")
            print(f"Stored {n} facts.")

    elif args.text:
        triples = extract_facts(args.text, domain=args.domain or "")
        print(json.dumps(triples, indent=2, ensure_ascii=False))
        if triples and not args.dry_run:
            n = store_facts(triples, domain=args.domain or "")
            print(f"Stored {n} facts.")

    elif args.batch:
        stats = run_batch(hours=args.hours, domain=args.domain, dry_run=args.dry_run)
        print(json.dumps(stats, indent=2))

    else:
        parser.print_help()
