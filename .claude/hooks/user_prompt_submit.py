#!/usr/bin/env python3
"""
DQIII8 Hook — UserPromptSubmit
Injects dynamic context into every user prompt Claude receives.

Output via stdout (plain text) is prepended to the prompt automatically
by Claude Code when the hook exits 0.

Rules:
- Prompt < 10 words → only inject active project (minimal)
- No active project → no output (total silence)
- Timeout 1s max → exit 0 without output
- Total output < 200 tokens (~800 chars)
"""

import json
import os
import re
import signal
import sqlite3
import sys
from pathlib import Path

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
PROJECTS_DIR = JARVIS / "projects"
LESSONS_FILE = JARVIS / "tasks" / "lessons.md"
DB = JARVIS / "database" / "dqiii8.db"

# ── Timeout guard ─────────────────────────────────────────────────────────────


def _timeout_handler(signum, frame):
    sys.exit(0)


signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(1)  # hard 1-second limit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _read_active_project() -> dict | None:
    """
    Find the most recently updated active project.
    Returns dict with keys: name, model, next_step, last_updated
    or None if no active project found.
    """
    if not PROJECTS_DIR.exists():
        return None

    candidates = []
    for md in PROJECTS_DIR.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        # Only consider files with status: active in frontmatter
        if not re.search(r"^status:\s*active", text, re.MULTILINE):
            continue
        # Extract last_updated
        m = re.search(r"^last_updated:\s*(.+)$", text, re.MULTILINE)
        last_updated = m.group(1).strip() if m else "0000-00-00"
        # Extract model
        m_model = re.search(r"^model:\s*(.+)$", text, re.MULTILINE)
        model = m_model.group(1).strip() if m_model else "unknown"
        # Extract next step — matches "Next step", "Próximo paso", etc.
        # Skips blank lines between header and content
        m_next = re.search(r"##\s*(?:[Nn]ext step|[Pp]r[oó]ximo paso)[^\n]*\n\s*\n*\**(.+)", text, re.IGNORECASE)
        next_step = m_next.group(1).strip().strip("*").strip() if m_next else ""
        # Truncate next_step to 120 chars
        if len(next_step) > 120:
            next_step = next_step[:117] + "..."
        candidates.append(
            {
                "name": md.stem,
                "model": model,
                "next_step": next_step,
                "last_updated": last_updated,
            }
        )

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["last_updated"], reverse=True)
    return candidates[0]


def _extract_keywords(prompt: str) -> list[str]:
    """Extract meaningful keywords from prompt (lowercase, >3 chars)."""
    stopwords = {
        "este",
        "esta",
        "esto",
        "como",
        "para",
        "que",
        "con",
        "una",
        "uno",
        "por",
        "los",
        "las",
        "del",
        "the",
        "this",
        "that",
        "with",
        "from",
        "and",
        "for",
        "are",
        "have",
        "what",
        "how",
        "can",
        "will",
        "more",
        "also",
        "not",
        "but",
        "all",
    }
    words = re.findall(r"[a-záéíóúñüA-ZÁÉÍÓÚÑÜ]{4,}", prompt.lower())
    return [w for w in words if w not in stopwords]


def _relevant_lessons(keywords: list[str], max_lines: int = 3) -> list[str]:
    """Return up to max_lines lessons matching any keyword."""
    if not LESSONS_FILE.exists() or not keywords:
        return []
    try:
        lines = LESSONS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    # Read from bottom (most recent first)
    matched = []
    for line in reversed(lines):
        if not line.strip() or not line.startswith("-"):
            continue
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            # Strip the leading "- " and keep compact
            matched.append(line.lstrip("- ").strip()[:160])
            if len(matched) >= max_lines:
                break
    return matched


def _spc_alert() -> str:
    """Return last active SPC trigger reason or empty string."""
    if not DB.exists():
        return ""
    try:
        conn = sqlite3.connect(str(DB), timeout=0.5)
        row = conn.execute(
            "SELECT reason FROM spc_metrics WHERE triggered=1 " "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt: str = data.get("prompt", "")
    if not prompt:
        sys.exit(0)

    word_count = len(prompt.split())

    # ── Find active project ──────────────────────────────────────────────────
    project = _read_active_project()
    if not project:
        sys.exit(0)  # silence: no active project

    # ── Minimal mode (< 10 words) ────────────────────────────────────────────
    if word_count < 10:
        print(
            f"─────────────────────────────────\n"
            f"[DQIII8 Context]\n"
            f"Active project: {project['name']} | Model: {project['model']}\n"
            f"─────────────────────────────────"
        )
        sys.exit(0)

    # ── Full mode ────────────────────────────────────────────────────────────
    keywords = _extract_keywords(prompt)
    lessons = _relevant_lessons(keywords)
    spc = _spc_alert()

    lines = [
        "─────────────────────────────────",
        "[DQIII8 Context]",
        f"Active project: {project['name']} | Model: {project['model']}",
    ]

    if project["next_step"]:
        lines.append(f"Next step: {project['next_step']}")

    if lessons:
        lines.append("Relevant lessons:")
        for lesson in lessons:
            lines.append(f"  · {lesson}")
    else:
        lines.append("Relevant lessons: none for this prompt")

    lines.append(f"SPC alert: {spc if spc else 'none'}")
    lines.append("─────────────────────────────────")

    output = "\n".join(lines)

    # Safety: never exceed ~800 chars (~200 tokens)
    if len(output) > 800:
        output = output[:797] + "..."

    print(output)
    sys.exit(0)


if __name__ == "__main__":
    main()
