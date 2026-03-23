#!/usr/bin/env python3
"""
auto_learner.py — Pattern-based auto-lesson generator ($0 cost, no LLM).

Components:
  - detect_auto_lessons(session_id, db_path) → (lessons_added, patterns_detected)
    Called from stop.py after each session.
  - consolidate_learning(db_path) → lessons_added
    Called from auditor.md to detect systemic patterns over 30 days.

Lesson prefix: [AUTO:keyword] — distinguishes from manual lessons.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

JARVIS = Path(__file__).parent.parent
LESSONS = JARVIS / "tasks" / "lessons.md"
DB_DEFAULT = JARVIS / "database" / "dqiii8.db"
NOW_UTC = datetime.now(timezone.utc)


# ── Helpers ────────────────────────────────────────────────────────────────


def extract_keyword(error_msg: str) -> str:
    """Derive a short keyword from an error message (max 30 chars, no spaces)."""
    if not error_msg:
        return "UnknownError"
    # Strip common prefixes
    msg = re.sub(r"^(exit code \d+|traceback.*?\n|error:)\s*", "", error_msg.lower())
    # Take first meaningful word cluster
    words = re.findall(r"[a-z][a-z0-9_]{2,}", msg)
    if not words:
        return "UnknownError"
    # Build CamelCase keyword from first 2 words
    kw = "".join(w.capitalize() for w in words[:2])
    return kw[:30] or "UnknownError"


def lesson_exists(keyword: str, lessons_text: str) -> bool:
    """Return True if keyword already appears in lessons_text (case-insensitive)."""
    return keyword.lower() in lessons_text.lower()


def append_lesson(lesson: str) -> None:
    """Append a lesson line to lessons.md under jarvis-core section."""
    if not LESSONS.exists():
        return
    content = LESSONS.read_text(encoding="utf-8")
    # Find jarvis-core section and append there
    marker = "## jarvis-core"
    if marker in content:
        idx = content.index(marker) + len(marker)
        # Find end of section header line
        newline_idx = content.index("\n", idx)
        content = content[: newline_idx + 1] + lesson + "\n" + content[newline_idx + 1 :]
    else:
        # Append at end
        content += lesson + "\n"
    LESSONS.write_text(content, encoding="utf-8")


# ── Component 1: Session-level detector ───────────────────────────────────


def detect_auto_lessons(session_id: str, db_path: str | Path | None = None) -> tuple[int, int]:
    """
    Detect auto-lessons for a completed session.

    Patterns checked:
      P1 — Repeat errors: same error_type seen 2+ times in last 7 days
      P2 — Retry-success: action failed then succeeded in same session
      P3 — Tier escalation: ESCALATION entries in error_log for this session

    Returns: (lessons_added, patterns_detected)
    """
    db_path = Path(db_path) if db_path else DB_DEFAULT
    if not db_path.exists():
        return 0, 0

    lessons_text = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""
    today = NOW_UTC.strftime("%Y-%m-%d")
    lessons_added = 0
    patterns_detected = 0

    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row

        # ── P1: Repeat errors (same error_type, 2+ occurrences, last 7 days) ──
        week_ago = (NOW_UTC - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        repeats = conn.execute(
            """
            SELECT error_type, COUNT(*) as cnt, MAX(error_message) as last_msg
            FROM error_log
            WHERE timestamp >= ?
              AND resolved = 0
              AND error_type IS NOT NULL
              AND error_type NOT IN ('ESCALATION')
            GROUP BY error_type
            HAVING cnt >= 2
            ORDER BY cnt DESC
            LIMIT 5
            """,
            (week_ago,),
        ).fetchall()

        for row in repeats:
            patterns_detected += 1
            kw = row["error_type"].replace(" ", "")[:30]
            if lesson_exists(f"[AUTO:{kw}]", lessons_text):
                continue
            lesson = (
                f"- [{today}] [AUTO:{kw}] "
                f"Repeated error {row['cnt']}x in 7d → review root cause. "
                f"Último: {(row['last_msg'] or '')[:60].replace(chr(10), ' ')}"
            )
            append_lesson(lesson)
            lessons_text += lesson  # update in-memory to avoid double-add
            lessons_added += 1

        # ── P2: Retry-success (tool failed then same tool succeeded, same session) ──
        retry_tools = conn.execute(
            """
            SELECT tool_used,
                   SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as fails,
                   SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as wins
            FROM agent_actions
            WHERE session_id = ?
              AND tool_used IS NOT NULL
            GROUP BY tool_used
            HAVING fails >= 1 AND wins >= 1
            ORDER BY fails DESC
            LIMIT 3
            """,
            (session_id,),
        ).fetchall()

        for row in retry_tools:
            patterns_detected += 1
            kw = f"RetrySuccess-{row['tool_used'].replace('__','').replace('_','')[:20]}"
            if lesson_exists(f"[AUTO:{kw}]", lessons_text):
                continue
            lesson = (
                f"- [{today}] [AUTO:{kw}] "
                f"{row['tool_used']} failed {row['fails']}x before success "
                f"→ verify preconditions or timeout"
            )
            append_lesson(lesson)
            lessons_text += lesson
            lessons_added += 1

        # ── P3: Tier escalation (ESCALATION in error_log this session) ──
        escalations = conn.execute(
            """
            SELECT agent_name, COUNT(*) as cnt,
                   MAX(error_message) as last_msg
            FROM error_log
            WHERE session_id = ?
              AND error_type = 'ESCALATION'
            GROUP BY agent_name
            ORDER BY cnt DESC
            LIMIT 3
            """,
            (session_id,),
        ).fetchall()

        for row in escalations:
            patterns_detected += 1
            agent = (row["agent_name"] or "unknown").replace("-", "")[:20]
            kw = f"TierEscalation-{agent}"
            if lesson_exists(f"[AUTO:{kw}]", lessons_text):
                continue
            lesson = (
                f"- [{today}] [AUTO:{kw}] "
                f"Agent {row['agent_name']} escalated {row['cnt']}x → "
                f"check if lower tier can resolve: {(row['last_msg'] or '')[:50].replace(chr(10), ' ')}"
            )
            append_lesson(lesson)
            lessons_text += lesson
            lessons_added += 1

        conn.close()

    except Exception:
        pass

    return lessons_added, patterns_detected


# ── Component 2: Weekly/audit consolidator ────────────────────────────────


def consolidate_learning(db_path: str | Path | None = None) -> int:
    """
    Detect systemic patterns over the last 30 days and resolve fixed ones.

    Patterns:
      S1 — Systemic errors: 5+ occurrences of same error_type in 30 days
      S2 — Resolved patterns: error_type that was repeating but resolved (0 in last 7d)

    Returns: lessons_added
    """
    db_path = Path(db_path) if db_path else DB_DEFAULT
    if not db_path.exists():
        return 0

    lessons_text = LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else ""
    today = NOW_UTC.strftime("%Y-%m-%d")
    lessons_added = 0

    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row

        month_ago = (NOW_UTC - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        week_ago = (NOW_UTC - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        # ── S1: Systemic errors (5+ in 30d) ──
        systemic = conn.execute(
            """
            SELECT error_type, COUNT(*) as cnt,
                   MAX(error_message) as last_msg,
                   MAX(timestamp) as last_seen
            FROM error_log
            WHERE timestamp >= ?
              AND error_type NOT IN ('ESCALATION')
              AND error_type IS NOT NULL
            GROUP BY error_type
            HAVING cnt >= 5
            ORDER BY cnt DESC
            LIMIT 5
            """,
            (month_ago,),
        ).fetchall()

        for row in systemic:
            patterns_detected_kw = f"SYSTEMIC-{row['error_type'].replace(' ', '')[:25]}"
            if lesson_exists(f"[AUTO:{patterns_detected_kw}]", lessons_text):
                continue
            lesson = (
                f"- [{today}] [AUTO:{patterns_detected_kw}] "
                f"Systemic error: {row['cnt']}x in 30d → prioritize structural fix. "
                f"Último: {row['last_seen'][:10]}"
            )
            append_lesson(lesson)
            lessons_text += lesson
            lessons_added += 1

        # ── S2: Resolved patterns (frequent in 30d but 0 in last 7d) ──
        resolved = conn.execute(
            """
            SELECT e30.error_type, e30.cnt as total_30d
            FROM (
                SELECT error_type, COUNT(*) as cnt
                FROM error_log
                WHERE timestamp >= ? AND timestamp < ?
                  AND error_type IS NOT NULL
                GROUP BY error_type
                HAVING cnt >= 3
            ) e30
            WHERE NOT EXISTS (
                SELECT 1 FROM error_log
                WHERE error_type = e30.error_type
                  AND timestamp >= ?
            )
            ORDER BY total_30d DESC
            LIMIT 3
            """,
            (month_ago, week_ago, week_ago),
        ).fetchall()

        for row in resolved:
            kw = f"RESOLVED-{row['error_type'].replace(' ', '')[:25]}"
            if lesson_exists(f"[AUTO:{kw}]", lessons_text):
                continue
            lesson = (
                f"- [{today}] [AUTO:{kw}] "
                f"Resolved pattern: {row['error_type']} ({row['total_30d']}x before, "
                f"0 in last 7d) → effective fix confirmed"
            )
            append_lesson(lesson)
            lessons_text += lesson
            lessons_added += 1

        conn.close()

    except Exception:
        pass

    return lessons_added


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DQIII8 auto-learner")
    parser.add_argument("--session", help="Session ID for detect mode")
    parser.add_argument("--consolidate", action="store_true", help="Run consolidator")
    parser.add_argument("--db", help="Path to dqiii8.db")
    args = parser.parse_args()

    db = args.db or None

    if args.consolidate:
        added = consolidate_learning(db)
        print(f"[auto-learner] consolidate: {added} systemic lessons added")
    elif args.session:
        added, patterns = detect_auto_lessons(args.session, db)
        print(f"[auto-learner] session {args.session[:8]}: {added} lecciones, {patterns} patrones")
    else:
        parser.print_help()
