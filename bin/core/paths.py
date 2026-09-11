"""
Central path constants for DQIII8.
All code must import from here — never hardcode /root/dqiii8 directly.
"""

import os
import re
from pathlib import Path

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]")

ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))

DB_PATH = ROOT / "database" / "dqiii8.db"
METRICS_DB_PATH = ROOT / "database" / "dqiii8_metrics.db"
SCHEMA_PATH = ROOT / "database" / "schema_v2.sql"

HOOKS_DIR = ROOT / ".claude" / "hooks"
AGENTS_DIR = ROOT / ".claude" / "agents"
SKILLS_DIR = ROOT / ".claude" / "skills"
RULES_DIR = ROOT / ".claude" / "rules"
RULES_DB_DIR = ROOT / ".claude" / "rules_db"

BIN_DIR = ROOT / "bin"
CORE_DIR = BIN_DIR / "core"
TASKS_DIR = ROOT / "tasks"
SESSIONS_DIR = ROOT / "sessions"
LOGS_DIR = Path("/var/log/dqiii8")
KNOWLEDGE_DIR = ROOT / "knowledge"
CONTEXT_DIR = ROOT / "context"
PROJECTS_DIR = ROOT / "projects"
MY_PROJECTS_DIR = ROOT / "my-projects"
CONFIG_DIR = ROOT / "config"
CDP_INVESTIGATE_OUT_DIR = ROOT / "tmp" / "cdp_investigate"


def safe_session_id(session_id: str, max_len: int = 128) -> str:
    """Sanitize an untrusted session_id for use in a filename (path traversal
    guard) — shared by every hook that keys a per-session state file on it
    (precompact.py, postcompact.py, user_prompt_submit.py). Was three
    identical copies of this regex+truncate before consolidation."""
    return _SAFE_ID_RE.sub("_", session_id)[:max_len] or "unknown"
