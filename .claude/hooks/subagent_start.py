#!/usr/bin/env python3
"""
DQIII8 Hook — SubagentStart
Fires when Claude Code spawns a subagent via the Task tool.
Payload fields: agent_id, agent_type, session_id, prompt (truncated).

Responsibilities:
1. Write /tmp/dqiii8_agent_{agent_id}.json for pre_tool_use lookup.
2. INSERT into agent_registry table.
3. Inject additionalContext with the resolved DQIII8 agent name.
"""

import sys
import json
import logging
import logging.handlers
import re
import time
import os
import subprocess
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
            logging.Formatter("%(asctime)s [subagent_start] %(levelname)s %(message)s")
        )
        log.addHandler(_fh)
    else:
        log.addHandler(logging.NullHandler())

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

agent_id = data.get("agent_id", "")
agent_type = data.get("agent_type", "")
session_id = data.get("session_id", "unknown")

# Reject a malformed agent_id before it is interpolated into any filesystem
# path or git branch name below — treat it the same as "absent" (both the
# worktree block and the lookup-file write are already gated on `agent_id`).
_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
if agent_id and not _AGENT_ID_RE.match(agent_id):
    log.warning(
        "subagent_start: agent_id failed format validation, treating as absent: %r", agent_id[:80]
    )
    agent_id = ""
timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

# ── Map agent_type to DQIII8 agent name ─────────────────────────────────────
AGENT_TYPE_MAP = {
    "python-specialist": "python-specialist",
    "git-specialist": "git-specialist",
    "code-reviewer": "code-reviewer",
    "orchestrator": "orchestrator",
    "auditor": "auditor",
    "content-automator": "content-automator",
    "data-analyst": "data-analyst",
    "creative-writer": "creative-writer",
}

# Resolve: prefer explicit agent_type match, fallback to agent_type as-is,
# then default to claude-sonnet-5
resolved_name = AGENT_TYPE_MAP.get(agent_type, agent_type or "claude-sonnet-5")

# ── Worktree isolation ───────────────────────────────────────────────────────
# Rango 3 (P0, 2026-08-19 red-team audit): parallel agents writing directly on
# the shared main tree with no isolation was a genuine data-race risk. User
# decision: worktree mandatory for every agent type, not just the 3 that
# previously opted in — every dispatched subagent with an agent_id now gets one.
worktree_path = ""

if agent_id:
    DQIII8_ROOT = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
    wt_dir = f"/tmp/dqiii8-wt/{agent_id}"
    branch = f"wt-{agent_id}"
    try:
        result = subprocess.run(
            ["git", "worktree", "add", wt_dir, "-b", branch],
            cwd=DQIII8_ROOT,
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0:
            worktree_path = wt_dir
        else:
            log.warning(
                "subagent_start: git worktree add exited %d: %s",
                result.returncode,
                result.stderr.decode("utf-8", errors="replace")[:500],
            )  # worktree failure must never block agent execution
    except Exception as e:
        log.warning(
            "subagent_start: git worktree creation failed: %s", e, exc_info=True
        )  # worktree failure must never block agent execution

# ── Step 1: Write lookup file (secure, no /tmp race condition) ───────────────
if agent_id:
    DQIII8_ROOT_PATH = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    secure_tmp = DQIII8_ROOT_PATH / "tmp"
    try:
        secure_tmp.mkdir(exist_ok=True, mode=0o700)
        tmp_path = secure_tmp / f"dqiii8_agent_{agent_id}.json"
        lookup = {
            "agent_id": agent_id,
            "agent_type": resolved_name,
            "parent_session_id": session_id,
            "timestamp": timestamp,
        }
        if worktree_path:
            lookup["worktree_path"] = worktree_path
        # Atomic write with restricted permissions (0o600) — prevents symlink attacks
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(lookup, f)
    except Exception as e:
        log.warning("subagent_start: agent lookup file write failed: %s", e, exc_info=True)

# ── Step 2: INSERT into agent_registry ──────────────────────────────────────
try:
    import sqlite3

    DB = os.path.join(
        os.environ.get("DQIII8_ROOT", "/root/dqiii8"),
        "database",
        "dqiii8.db",
    )
    if os.path.exists(DB):
        conn = sqlite3.connect(DB, timeout=2)
        conn.execute(
            "INSERT INTO agent_registry (agent_id, agent_type, parent_session, start_time) "
            "VALUES (?, ?, ?, ?)",
            (agent_id, resolved_name, session_id, timestamp),
        )
        conn.commit()
        conn.close()
except Exception as e:
    log.warning(
        "subagent_start: agent_registry INSERT failed: %s", e, exc_info=True
    )  # logging never blocks execution

# ── Step 3: Inject additionalContext ────────────────────────────────────────
ctx = (
    f"[DQIII8] You are the '{resolved_name}' agent. "
    f"agent_id={agent_id} parent_session={session_id}. "
    f"Write results to tasks/results/{resolved_name}-{timestamp[:10]}.md."
)
if worktree_path:
    ctx += (
        f" Your isolated working directory is {worktree_path}. "
        f"When done, clean up with: git worktree remove --force {worktree_path}"
    )
log.info(
    "injected agent_id=%s type=%s worktree=%s chars=%d",
    agent_id,
    resolved_name,
    bool(worktree_path),
    len(ctx),
)
print(json.dumps({"additionalContext": ctx}))

sys.exit(0)
