#!/usr/bin/env python3
"""
DQIII8 — PermissionAnalyzer v3
Centralized permission evaluation for pre_tool_use hooks.

v2: SQLite timeout + ALLOWED_DELETIONS + ESCALATE loop
v3: Dual-channel rejections (BD + JSON buzón) + budget check +
    autonomous auto-approve + FIX ESCALATE count (DENY+ESCALATE)
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

# ── Configuration ───────────────────────────────────────────────────────────
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")
JARVIS_MODE = os.environ.get("JARVIS_MODE", "supervised")

# ── Risk constants ──────────────────────────────────────────────────────────
BLOCKED_PATHS = [
    ".env",
    "secrets",
    "jarvis_metrics.db",
    ".claude/settings.json",
    "CLAUDE.md",
    "schema.sql",
    ".git/",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "context/proposito.md",
]

HIGH_RISK_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf /anything (includes rm -rf /)
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\$HOME",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM\s+agent_actions\b(?!\s+WHERE)",  # solo sin WHERE (mass-delete)
    r"DROP\s+DATABASE",
    r">\s+/dev/sda",
    r"\bmkfs\b",
    r"\bdd\b.*\bif=",
    r"chmod\s+777\s+/",
    r":\(\)\s*\{.*:\|:.*\}",  # fork bomb
]

ALLOWED_DELETIONS = [
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "tmp",
    "/tmp/",
    ".mypy_cache",
    "*.pyc",
    ".ruff_cache",
]

# Project directories always safe for writing
SAFE_PROJECT_DIRS = [
    "/root/jarvis/",
    "/root/math-image-generator",
    "/tmp/",
]

# Tools auto-approved in autonomous mode (after passing checks)
AUTO_APPROVE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
}

MAX_SESSION_COST_USD = 5.0
MAX_SAME_REJECTION = 2  # After 2 identical rejections → ESCALATE

# Informational hints per denial type (help Claude self-correct)
DENIAL_HINTS: dict[str, str] = {
    "blocked_path:.env": (
        "Use os.environ['KEY'] to read temporary variables. "
        "Or use export KEY=value in bash without touching the file."
    ),
    "blocked_path:schema.sql": (
        "Add the SQL migration in a new file: "
        "database/migrations/YYYYMMDD_description.sql"
    ),
    "blocked_path:CLAUDE.md": (
        "System instructions are not modified from code. "
        "The user updates them manually."
    ),
    "blocked_path:jarvis_metrics.db": (
        "Use INSERT/UPDATE via sqlite3 with the existing wrapper. "
        "Do not modify the DB file directly."
    ),
    "blocked_path:context/proposito.md": (
        "The system purpose can only be modified by the user directly. "
        "No agent can edit this file."
    ),
    "high_risk_pattern": (
        "Use specific relative paths instead of wildcards. "
        "Or add the pattern to ALLOWED_DELETIONS if it is cache cleanup."
    ),
    "budget_exceeded": (
        "Split the objective into smaller subtasks. "
        "Start a new session with j --autonomous"
    ),
    "repeat_rejection": (
        "This action was rejected multiple times. "
        "Change strategy: use a different tool or "
        "ask the user before retrying."
    ),
}


class PermissionAnalyzer:
    """Centralized permission evaluator for Claude Code tools."""

    def evaluate(self, tool: str, inp: dict, session_id: str | None = None) -> dict:
        """
        Evaluates whether a tool can execute.
        decision ∈ {APPROVE, DENY, ESCALATE}

        session_id: Hook event session ID (takes priority over environment variable).
        """
        _session = session_id or SESSION_ID
        detail = str(inp.get("file_path", inp.get("command", "")))

        # 0a. Safe project directories — fast-path (respects BLOCKED_PATHS)
        if tool in ("Write", "Edit", "MultiEdit"):
            file_path = inp.get("file_path", inp.get("path", ""))
            if any(safe in file_path for safe in SAFE_PROJECT_DIRS):
                if not any(blocked in file_path for blocked in BLOCKED_PATHS):
                    return self._approve("Safe project directory", "LOW", "safe_project_dir")
        elif tool == "Bash":
            # For Bash: fast-path only for output/tmp directories (not project paths)
            bash_safe = ["/tmp/"]
            if any(safe in detail for safe in bash_safe):
                return self._approve("Safe output directory", "LOW", "safe_project_dir")

        # 0b. learned_approvals — fast-path for historically safe patterns
        if self._is_learned_safe(tool, detail):
            return self._approve("Pattern approved by history", "LOW", "learned_approval")

        # 1. ESCALATE — closes infinite loops
        escalate = self._check_repeat_rejections(tool, detail, _session)
        if escalate:
            return escalate

        # 2. Budget — block if session budget is exceeded
        budget_deny = self._check_budget(_session)
        if budget_deny:
            return budget_deny

        # 3. Blocked paths (Write, Edit, MultiEdit)
        if tool in ("Edit", "Write", "MultiEdit"):
            path = inp.get("file_path", inp.get("path", ""))
            for blocked in BLOCKED_PATHS:
                if blocked in path:
                    return self._deny(
                        tool,
                        path,
                        f"Write blocked at '{path}'. "
                        "Edit this file manually if needed.",
                        "CRITICAL",
                        f"blocked_path:{blocked}",
                        "Edit directly from terminal or ask the user.",
                    )

        # 3b. Resource claims — block if another agent holds the file
        if tool in ("Edit", "Write", "MultiEdit"):
            path = inp.get("file_path", inp.get("path", ""))
            claim_deny = self._check_resource_claim(tool, path, _session)
            if claim_deny:
                return claim_deny

        # 4. High-risk commands with ALLOWED_DELETIONS exception
        if tool == "Bash":
            cmd = inp.get("command", "")
            for pattern in HIGH_RISK_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    is_safe_deletion = any(safe in cmd for safe in ALLOWED_DELETIONS)
                    if is_safe_deletion:
                        break
                    if JARVIS_MODE == "autonomous":
                        return self._deny(
                            tool,
                            cmd,
                            f"High-risk command in autonomous mode: {cmd[:80]}",
                            "HIGH",
                            f"high_risk_pattern:{pattern}",
                            "Use ALLOWED_DELETIONS or run in supervised mode.",
                        )
                    else:
                        return self._deny(
                            tool,
                            cmd,
                            f"Blocked command: '{cmd[:80]}'",
                            "CRITICAL",
                            f"high_risk_pattern:{pattern}",
                            "This command is destructive and irreversible.",
                        )

        # 5. Autonomous mode — auto-approve standard tools (after checks)
        if JARVIS_MODE == "autonomous" and tool in AUTO_APPROVE_TOOLS:
            return self._approve("autonomous_mode")

        return self._approve()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _approve(
        self,
        reason: str = "OK",
        risk_level: str = "LOW",
        rule_triggered: str | None = None,
    ) -> dict:
        return {
            "decision": "APPROVE",
            "reason": reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
            "suggested_fix": None,
        }

    def _deny(
        self,
        tool: str,
        detail: str,
        reason: str,
        risk_level: str,
        rule_triggered: str,
        suggested_fix: str,
    ) -> dict:
        # Enrich reason with self-correction hint
        enriched_reason = reason
        if rule_triggered:
            for key, hint in DENIAL_HINTS.items():
                if key in rule_triggered:
                    enriched_reason = f"{reason} | Alternative: {hint}"
                    break
        return {
            "decision": "DENY",
            "reason": enriched_reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
            "suggested_fix": suggested_fix,
        }

    def _check_repeat_rejections(
        self, tool: str, detail: str, session_id: str | None = None
    ) -> dict | None:
        """
        If the same tool+action_detail has been rejected MAX_SAME_REJECTION
        times (DENY or ESCALATE) in this session → return ESCALATE.
        FIX C: counts both DENY and ESCALATE.
        """
        _session = session_id or SESSION_ID
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT COUNT(*) FROM permission_decisions
                WHERE session_id = ?
                  AND tool_name = ?
                  AND action_detail LIKE ?
                  AND decision IN ('DENY', 'ESCALATE')
                  AND timestamp > datetime('now', '-2 hours')
                """,
                (_session, tool, f"%{detail[:50]}%"),
            ).fetchone()
            conn.close()

            count = row[0] if row else 0
            if count >= MAX_SAME_REJECTION:
                return {
                    "decision": "ESCALATE",
                    "reason": (
                        f"Action '{tool}: {detail[:60]}' rejected "
                        f"{count} times in this session. "
                        "Requires human decision."
                    ),
                    "risk_level": "HIGH",
                    "rule_triggered": f"repeat_rejection:{count}",
                    "suggested_fix": (
                        "OrchestratorLoop must pause and notify the user. "
                        "The agent needs a different strategy that does not "
                        "require this blocked action. "
                        f"Previous attempts: {count}."
                    ),
                }
        except Exception:
            pass
        return None

    def _is_learned_safe(self, tool: str, detail: str) -> bool:
        """
        Checks if this tool+pattern has already been approved >= 3 times (active=1).
        Fast-path before all security checks.
        """
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT id FROM learned_approvals
                WHERE tool_name = ?
                  AND ? LIKE '%' || pattern || '%'
                  AND active = 1
                LIMIT 1
                """,
                (tool, detail),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def _check_resource_claim(self, tool: str, path: str, session_id: str) -> dict | None:
        """
        Blocks if another agent/session holds an active claim on this resource.
        Claims expire automatically by TTL (expires_at).
        """
        if not path:
            return None
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT agent, session_id FROM resource_claims
                WHERE resource = ?
                  AND session_id != ?
                  AND expires_at > datetime('now')
                LIMIT 1
                """,
                (path, session_id),
            ).fetchone()
            conn.close()
            if row:
                holder_agent, holder_session = row
                return self._deny(
                    tool,
                    path,
                    f"Resource '{path}' locked by agent '{holder_agent}' "
                    f"(session {holder_session[:8]}…). Wait for the claim to expire.",
                    "MEDIUM",
                    "resource_claim",
                    "Wait 30 min or ask the owning agent to release the resource.",
                )
        except Exception:
            pass
        return None

    def _check_budget(self, session_id: str) -> dict | None:
        """Blocks if estimated session cost exceeds MAX_SESSION_COST_USD."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_used),0) FROM agent_actions "
                "WHERE session_id=? AND timestamp > datetime('now','-1 hour')",
                (session_id,),
            ).fetchone()
            conn.close()
            session_tokens = row[0] if row else 0
            estimated_cost = (session_tokens / 1_000_000) * 15.0
            if estimated_cost > MAX_SESSION_COST_USD:
                return self._deny(
                    "budget",
                    f"${estimated_cost:.2f}",
                    f"Session budget exceeded: "
                    f"${estimated_cost:.2f} > ${MAX_SESSION_COST_USD}",
                    "HIGH",
                    "budget_exceeded",
                    "Split the objective into smaller subtasks. "
                    "Start a new session with j --autonomous",
                )
        except Exception:
            pass
        return None


# ── Standalone functions (used by pre_tool_use.py) ──────────────────────────


def _notify_telegram_activation(tool_name: str, pattern: str) -> None:
    """Fire-and-forget Telegram alert when a pattern auto-activates at times_seen=3."""
    try:
        import requests
        from dotenv import load_dotenv

        load_dotenv(str(JARVIS_ROOT / ".env"))
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        msg = (
            "🔓 *Auto-approval activated*\n"
            f"`{tool_name}` → `{pattern[:80]}`\n"
            "Seen: 3 times. Active for future uses."
        )
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception:
        pass  # never block the pipeline


def record_decision(tool: str, inp: dict, result: dict) -> None:
    """
    Records APPROVE decisions in the DB.
    For LOW risk approvals: auto-learns the pattern in learned_approvals
    when seen >= 3 times (activates the record).
    """
    if result["decision"] != "APPROVE":
        return
    action_detail = str(inp.get("file_path", inp.get("command", "")))[:200]
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason, risk_level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                action_detail,
                "APPROVE",
                result.get("reason", "OK"),
                result.get("risk_level", "LOW"),
            ),
        )
        # Auto-learning for low-risk patterns
        if result.get("risk_level") == "LOW" and result.get("reason") != "learned_approval":
            pattern = action_detail[:50].strip()
            if pattern:
                conn.execute(
                    """
                    INSERT INTO learned_approvals
                        (tool_name, pattern, times_seen, last_seen, active)
                    VALUES (?, ?, 1, datetime('now'), 0)
                    ON CONFLICT(tool_name, pattern) DO UPDATE SET
                        times_seen = times_seen + 1,
                        last_seen  = datetime('now'),
                        active     = CASE WHEN times_seen + 1 >= 3 THEN 1 ELSE 0 END
                    """,
                    (tool, pattern),
                )
                # Notify if this upsert just auto-activated the pattern (times_seen=3)
                row = conn.execute(
                    "SELECT times_seen, active FROM learned_approvals "
                    "WHERE tool_name=? AND pattern=?",
                    (tool, pattern),
                ).fetchone()
                if row and row[0] == 3 and row[1] == 1:
                    _notify_telegram_activation(tool, pattern)
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_rejection(tool: str, inp: dict, result: dict) -> None:
    """
    Records DENY and ESCALATE in two channels:
    Channel 1 — DB: permission_decisions table
    Channel 2 — JSON mailbox: tasks/permission_rejection.json (read by OrchestratorLoop)
    FIX A: added JSON channel.
    """
    if result["decision"] not in ("DENY", "ESCALATE"):
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": SESSION_ID,
        "tool_name": tool,
        "action_detail": str(inp.get("file_path", inp.get("command", "")))[:200],
        "decision": result["decision"],
        "reason": result.get("reason", ""),
        "risk_level": result.get("risk_level", ""),
        "rule_triggered": result.get("rule_triggered", ""),
        "suggested_fix": result.get("suggested_fix", ""),
    }

    # Channel 1: DB
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason,
                 risk_level, rule_triggered, suggested_fix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                entry["action_detail"],
                entry["decision"],
                entry["reason"],
                entry["risk_level"],
                entry["rule_triggered"],
                entry["suggested_fix"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Channel 2: JSON mailbox (append to array)
    try:
        reject_path = JARVIS_ROOT / "tasks" / "permission_rejection.json"
        existing: list = []
        if reject_path.exists():
            try:
                existing = json.loads(reject_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.append(entry)
        reject_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
