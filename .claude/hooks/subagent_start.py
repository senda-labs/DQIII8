#!/usr/bin/env python3
"""
DQIII8 Hook — SubagentStart
Fires when Claude Code spawns a subagent via the Task tool.
Payload fields: agent_id, agent_type, session_id, prompt (truncated).

Responsibilities:
1. Write /tmp/jarvis_agent_{agent_id}.json for pre_tool_use lookup.
2. INSERT into agent_registry table.
3. Inject additionalContext with the resolved DQIII8 agent name.
"""

import sys
import json
import time
import os
import subprocess
from pathlib import Path

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

agent_id = data.get("agent_id", "")
agent_type = data.get("agent_type", "")
session_id = data.get("session_id", "unknown")
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
# then default to claude-sonnet-4-6
resolved_name = AGENT_TYPE_MAP.get(agent_type, agent_type or "claude-sonnet-4-6")

# ── Worktree isolation ───────────────────────────────────────────────────────
WORKTREE_AGENTS = {"code-reviewer", "python-specialist", "orchestrator"}
worktree_path = ""

if resolved_name in WORKTREE_AGENTS and agent_id:
    DQIII8_ROOT = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
    wt_dir = f"/tmp/jarvis-wt/{agent_id}"
    branch = f"wt-{agent_id[:8]}"
    try:
        subprocess.run(
            ["git", "worktree", "add", wt_dir, "-b", branch],
            cwd=DQIII8_ROOT,
            capture_output=True,
            timeout=15,
        )
        worktree_path = wt_dir
    except Exception:
        pass  # worktree failure must never block agent execution

# ── Step 1: Write lookup file (secure, no /tmp race condition) ───────────────
if agent_id:
    DQIII8_ROOT_PATH = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    secure_tmp = DQIII8_ROOT_PATH / "tmp"
    try:
        secure_tmp.mkdir(exist_ok=True, mode=0o700)
        tmp_path = secure_tmp / f"jarvis_agent_{agent_id}.json"
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
    except Exception:
        pass

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
except Exception:
    pass  # logging never blocks execution

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
print(json.dumps({"additionalContext": ctx}))

sys.exit(0)
