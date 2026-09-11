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
import logging.handlers
import os
import re
import signal
import sqlite3
import sys
from pathlib import Path

log = logging.getLogger("dqiii8." + __name__)
if not log.handlers:
    log.setLevel(logging.DEBUG)
    _log_dir = Path("/var/log/dqiii8")
    if _log_dir.exists():
        _fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "hooks.log"), maxBytes=2_000_000, backupCount=3
        )
        _fh.setFormatter(
            logging.Formatter("%(asctime)s [user_prompt_submit] %(levelname)s %(message)s")
        )
        log.addHandler(_fh)
    else:
        log.addHandler(logging.NullHandler())

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
    m_next = re.search(
        r"##\s*(?:[Nn]ext step|[Pp]r[oó]ximo paso)[^\n]*\n\s*\n*\**(.+)", text, re.IGNORECASE
    )
    next_step = m_next.group(1).strip().strip("*").strip("|").strip() if m_next else ""
    if len(next_step) > 120:
        next_step = next_step[:117] + "..."
    return {
        "name": md_path.parent.name,
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
    """Write-layer NL matcher: explicit verb + exact known-project token. No match -> None.

    Checks the regex-captured candidate against a named path instead of
    enumerating my-projects/ (docs/plglobal/README.md finding #41 — same fix
    as _project_by_name/#37: operators hold a traverse-only ACL there, no
    read bit, so a directory listing silently returns empty/raises for them).
    The candidate is already a single known token from the regex capture, so
    a named-path existence check is both correct and sufficient here — no
    real enumeration is ever needed for this matcher.
    """
    m = _NL_VERB_RE.search(prompt)
    if not m:
        return None
    candidate = m.group(1).lower()
    if candidate == "dqiii8-core":
        return "dqiii8-core"
    if (PROJECTS_DIR / candidate).is_dir():
        return candidate
    return None


def _log_nl_shadow_candidate(
    prompt: str, matched_project: str, confidence: float, agreed: bool
) -> None:
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


def _project_by_name(name: str) -> dict | None:
    """Load one project by exact slug via a named path, not a directory
    listing. Operator sessions (plglobal-isabel/mario) hold a traverse-only
    ACL on my-projects/ (no read bit — docs/plglobal/README.md finding #11):
    stat/read on a named child path still works, iterdir()/glob() over the
    parent does not (silently returns empty, PermissionError swallowed by
    glob's own scandir handling). Same named-path pattern postcompact.py
    already uses for next_step."""
    md = PROJECTS_DIR / name / "PROJECT.md"
    if md.exists():
        return _parse_project_file(md)
    return None


def _read_active_project(prompt: str = "", session_id: str = "", cwd: str | None = None) -> dict | None:
    """
    Find the relevant project: explicit prompt mention > project_context SSOT
    (same resolve_project_safe() session_start.py/postcompact.py use) > most
    recently updated project file (fail-open fallback if the SSOT lookup
    breaks or returns nothing).
    Returns dict with keys: name, next_step, last_updated, tags
    or None if no active project found.

    `projects` (a full my-projects/ listing) can be legitimately empty for an
    operator session even when a project IS active — do not early-return on
    that alone, or SSOT resolution below never runs for them at all.
    """
    projects = _load_all_projects()
    if prompt and projects:
        matched = _detect_project_from_prompt(prompt, projects)
        if matched:
            return matched
    try:
        from core.action_log import resolve_project_safe

        ssot_name = resolve_project_safe(session_id, cwd=cwd)
        if ssot_name:
            for p in projects:
                if p["name"] == ssot_name:
                    return p
            if ssot_name == "dqiii8-core":
                return {
                    "name": "dqiii8-core",
                    "next_step": "",
                    "last_updated": 0,
                    "tags": {"dqiii8-core"},
                }
            direct = _project_by_name(ssot_name)
            if direct:
                return direct
    except Exception as e:
        log.debug("SSOT project resolution skipped: %s", e)
    return projects[0] if projects else None


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
        log.warning(
            "user_prompt_submit: _log_skill_invocation skill_metrics write failed: %s",
            e,
            exc_info=True,
        )


def _ups_state_file(session_id: str) -> Path:
    from core.paths import safe_session_id

    return DQIII8 / "tasks" / f"ups_state_{safe_session_id(session_id)}.json"


def _last_project_name(session_id: str) -> str | None:
    """Anti context-rot (#36): last project name this hook injected for this
    session, so an unchanged minimal-mode turn ('sigue', 'dale', 'ok'...) can
    be silenced instead of re-asserting identical, zero-new-info identity."""
    if not session_id:
        return None
    try:
        return json.loads(_ups_state_file(session_id).read_text(encoding="utf-8")).get("project")
    except Exception:
        return None


def _save_last_project_name(session_id: str, project_name: str, previous: str | None) -> None:
    if not session_id or project_name == previous:
        return  # unchanged: skip the write, not just the injection
    try:
        f = _ups_state_file(session_id)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"project": project_name}), encoding="utf-8")
        os.replace(tmp, f)
    except Exception as e:
        log.debug("ups state save skipped: %s", e)


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
                prompt,
                shadow_match["name"],
                confidence=0.5,
                agreed=(nl_match == shadow_match["name"]),
            )
    except Exception as e:
        log.debug("NL project matcher skipped: %s", e)

    session_id = data.get("session_id", "")

    # ── Find active project (explicit mention > SSOT > most-recent fallback) ──
    project = _read_active_project(prompt=prompt, session_id=session_id, cwd=data.get("cwd"))
    if not project:
        sys.exit(0)  # silence: no active project

    model = os.environ.get("DQIII8_MODEL", "claude-sonnet-5")
    previous_project = _last_project_name(session_id)

    # ── Minimal mode (< 10 words) ────────────────────────────────────────────
    if word_count < 10:
        # #36 anti context-rot: an unchanged trivial turn ("sigue", "dale",
        # "ok"...) carries zero new information over the last injection for
        # this session — re-asserting the identical identity block every
        # single such turn is exactly the low-signal repetition the context
        # engineering guidance warns against. Silence instead of repeat.
        if previous_project == project["name"]:
            sys.exit(0)
        _save_last_project_name(session_id, project["name"], previous_project)
        print(
            f"─────────────────────────────────\n"
            f"[DQIII8 Context]\n"
            f"Active project: {project['name']} | Model: {model}\n"
            f"─────────────────────────────────"
        )
        sys.exit(0)

    # ── Full mode ────────────────────────────────────────────────────────────
    # Always emitted (not state-diffed): lessons/SPC alert are recomputed per
    # prompt and can carry new signal even when the project itself hasn't
    # changed, unlike minimal mode's fixed, content-free identity block.
    _save_last_project_name(session_id, project["name"], previous_project)
    keywords = _extract_keywords(prompt)
    lessons = _relevant_lessons(keywords)
    spc = _spc_alert()

    lines = [
        "─────────────────────────────────",
        "[DQIII8 Context]",
        f"Active project: {project['name']} | Model: {model}",
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
