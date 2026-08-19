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
import logging
import os
import re
import signal
import sqlite3
import sys
from pathlib import Path

log = logging.getLogger("dqiii8." + __name__)

DQIII8 = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
sys.path.insert(0, str(DQIII8 / "bin"))
# Correction C fix: the old projects/ dir doesn't exist — real project docs
# live at my-projects/<slug>/PROJECT.md, one level deeper.
PROJECTS_DIR = DQIII8 / "my-projects"
LESSONS_FILE = DQIII8 / "tasks" / "lessons.md"
DB = DQIII8 / "database" / "dqiii8.db"

# ── NL project-declaration matcher (D2, two-layer design) ────────────────────
# Write layer: narrow, high-precision. An explicit verb immediately followed
# by a token that exactly matches a known project name. No match -> no write.
_NL_VERB_RE = re.compile(
    r"\b(?:trabaj\w+\s+(?:sobre|en|con)|estamos\s+con|cambio\s+a|switch(?:ing)?\s+to|working\s+on)\s+"
    r"([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)

# ── Timeout guard ─────────────────────────────────────────────────────────────


def _timeout_handler(signum, frame):
    sys.exit(0)


signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(1)  # hard 1-second limit


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_project_file(md_path) -> dict | None:
    """Parse a my-projects/<slug>/PROJECT.md file into a metadata dict.

    These files have no status:/tags: frontmatter (that format belonged to
    the old, nonexistent projects/*.md layout — Correction C); every dir
    under my-projects/ with a PROJECT.md is a real, known project.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return None
    m_next = re.search(r"##\s*(?:[Nn]ext step|[Pp]r[oó]ximo paso)[^\n]*\n\s*\n*\**(.+)", text, re.IGNORECASE)
    next_step = m_next.group(1).strip().strip("*").strip("|").strip() if m_next else ""
    if len(next_step) > 120:
        next_step = next_step[:117] + "..."
    return {
        "name": md_path.parent.name,
        "model": "unknown",
        "next_step": next_step,
        "last_updated": md_path.stat().st_mtime,
        "tags": {md_path.parent.name},
    }


def _load_all_projects() -> list[dict]:
    """Return all known projects from my-projects/<slug>/PROJECT.md, newest mtime first."""
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for md in PROJECTS_DIR.glob("*/PROJECT.md"):
        p = _parse_project_file(md)
        if p:
            projects.append(p)
    projects.sort(key=lambda x: x["last_updated"], reverse=True)
    return projects


def _nl_match_project(prompt: str) -> str | None:
    """Write-layer NL matcher: explicit verb + exact known-project token. No match -> None."""
    m = _NL_VERB_RE.search(prompt)
    if not m:
        return None
    candidate = m.group(1).lower()
    for name in _known_project_names():
        if name.lower() == candidate:
            return name
    return None


def _known_project_names() -> set[str]:
    if not PROJECTS_DIR.exists():
        return {"dqiii8-core"}
    return {p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()} | {"dqiii8-core"}


def _log_nl_shadow_candidate(prompt: str, matched_project: str, confidence: float, agreed: bool) -> None:
    """Shadow layer: log fuzzy-match candidates for recall measurement, never used for attribution."""
    if not DB.exists():
        return
    try:
        conn = sqlite3.connect(str(DB), timeout=0.5)
        conn.execute(
            "INSERT INTO nl_match_candidates "
            "(prompt_excerpt, matched_project, confidence, matched_at, precision_matcher_agreed) "
            "VALUES (?, ?, ?, datetime('now'), ?)",
            (prompt[:200], matched_project, confidence, 1 if agreed else 0),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.debug("nl_match_candidates shadow write skipped: %s", e)


def _detect_project_from_prompt(prompt: str, projects: list[dict]) -> dict | None:
    """
    Check if the prompt explicitly mentions any known project by name or tag.
    Returns the matching project dict, or None.
    Matches are case-insensitive and handle hyphens as spaces/hyphens.
    """
    prompt_lower = prompt.lower()
    for project in projects:
        for tag in project["tags"]:
            tag_normalized = tag.lower().replace("-", "[ -]?")
            if re.search(r"\b" + tag_normalized + r"\b", prompt_lower):
                return project
    return None


def _read_active_project(prompt: str = "") -> dict | None:
    """
    Find the relevant project: prompt keyword match > most recently updated active.
    Returns dict with keys: name, model, next_step, last_updated, tags
    or None if no active project found.
    """
    projects = _load_all_projects()
    if not projects:
        return None
    if prompt:
        matched = _detect_project_from_prompt(prompt, projects)
        if matched:
            return matched
    return projects[0]


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
    matched = []
    for line in reversed(lines):
        if not line.strip() or not line.startswith("-"):
            continue
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            matched.append(line.lstrip("- ").strip()[:160])
            if len(matched) >= max_lines:
                break
    return matched


def _log_skill_invocation(skill_name: str) -> None:
    """UPSERT into skill_metrics when a /skill is invoked."""
    if not DB.exists():
        return
    try:
        conn = sqlite3.connect(str(DB), timeout=0.5)
        ex = conn.execute(
            "SELECT id FROM skill_metrics WHERE skill_name=?", (skill_name,)
        ).fetchone()
        if ex:
            conn.execute(
                "UPDATE skill_metrics SET times_loaded=times_loaded+1 WHERE skill_name=?",
                (skill_name,),
            )
        else:
            conn.execute(
                "INSERT INTO skill_metrics (skill_name, times_loaded) VALUES (?, 1)",
                (skill_name,),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("user_prompt_submit: _log_skill_invocation skill_metrics write failed: %s", e, exc_info=True)


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

    # ── Skill invocation logging ─────────────────────────────────────────────
    skill_m = re.match(r"^/([a-zA-Z0-9_:/-]+)", prompt.strip())
    if skill_m:
        _log_skill_invocation(skill_m.group(1).lower())

    # ── NL project declaration (D2, two-layer) ───────────────────────────────
    # Write layer: a real match here declares the project (project_context,
    # scope=session_id) so later resolve_project() calls for this session
    # pick it up via the DB-backed SSOT (bin/core/project_context.py).
    try:
        nl_match = _nl_match_project(prompt)
        if nl_match:
            from core.project_context import set_project

            session_id = data.get("session_id", "")
            if session_id:
                set_project(nl_match, scope=session_id, declared_by="prompt", validate=False)
        # Shadow layer: independent fuzzy tag matcher, log-only, never writes
        # project_context — measures recall the strict write-layer above misses.
        _projects_for_shadow = _load_all_projects()
        shadow_match = _detect_project_from_prompt(prompt, _projects_for_shadow)
        if shadow_match:
            _log_nl_shadow_candidate(
                prompt, shadow_match["name"], confidence=0.5,
                agreed=(nl_match == shadow_match["name"]),
            )
    except Exception as e:
        log.debug("NL project matcher skipped: %s", e)

    # ── Find active project (keyword match first, then most-recent fallback) ──
    project = _read_active_project(prompt=prompt)
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
