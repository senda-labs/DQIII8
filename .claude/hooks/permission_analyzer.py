#!/usr/bin/env python3
"""
DQIII8 — PermissionAnalyzer v3
Centralized permission evaluation for pre_tool_use hooks.

v2: SQLite timeout + ALLOWED_DELETIONS + ESCALATE loop
v3: Dual-channel rejections (DB + JSON inbox) + budget check +
    autonomous auto-approve + FIX ESCALATE count (DENY+ESCALATE)
v3.1: BLOCKED_PATHS Bash enforcement, CLAUDE_MD_PLUGIN_EDIT bypass removal,
      in-process fallback counter, defensive pattern check wrapping
"""

import json
import logging
import os
import re
import sqlite3
import threading as _threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("dqiii8." + __name__)

# ── Configuration ───────────────────────────────────────────────────────────
DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")
DQIII8_MODE = os.environ.get("DQIII8_MODE", "supervised")

# ── Risk constants ──────────────────────────────────────────────────────────
BLOCKED_PATHS = [
    "CLAUDE.md",
    ".env",
    "secrets",
    "dqiii8.db",
    ".claude/settings.json",
    "schema.sql",
    ".git/",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "context/proposito.md",
]

# Paths where even READ is dangerous (credential exfiltration risk).
# Literal fast-path tokens only; the authoritative matcher is _credential_hit()
# below, which also covers suffix classes (.pem/.key/.p12/.pfx) and non-dotfile
# env files (prod.env, config/app.env) that a literal substring cannot express.
BASH_CREDENTIAL_PATHS = [
    ".credentials.json",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    ".gnupg/",
]

# ── Credential-path gate (v3.3) ─────────────────────────────────────────────
# Single source of truth shared by the read family (Read/Grep/Glob, step 3d)
# and by Bash (step 3c), so the three read-family tools and the shell can never
# drift apart: a path blocked for one is blocked for all.
#
# Deliberately NOT BLOCKED_PATHS: that list is a *write* denylist and also
# contains files that must stay readable (CLAUDE.md, dqiii8.db, schema.sql,
# .claude/settings.json, context/proposito.md). This gate covers genuine
# credential material only.
#
# Directory components — any path segment equal to one of these is credential
# territory (covers the ".ssh/" / ".gnupg/" entries of BASH_CREDENTIAL_PATHS).
CREDENTIAL_DIRS = {".ssh", ".secrets", ".gnupg"}

# Template files carry placeholders, never real values (13 committed
# *.env.example files in this repo). Allowlisted so widening the env rule to
# non-dotfile forms does not make routine setup work impossible.
_CREDENTIAL_TEMPLATE_RE = re.compile(r"\.(?:example|sample|template|dist)$", re.IGNORECASE)

# Basenames — matched against the file name, not the whole path, so that
# source files that merely mention secrets (bin/core/human_pending/secrets.py,
# alembic/022_wallet_pass_secrets.py, SECRETPOWER.yaml) stay readable.
_CREDENTIAL_BASENAME_RE = re.compile(
    r"^(?:"
    r".*\.env(?:\..+)?"          # .env, .env.local, prod.env, config/app.env
    r"|\.credentials\.json"      # OAuth credential store
    r"|id_rsa.*|id_ed25519.*"    # private keys (and their .pub siblings)
    r"|\.secrets"                # dotfile secret store
    r"|.*secrets?\.json"         # client_secret.json, youtube_client_secret.json
    r"|.+\.(?:pem|key|p12|pfx)"  # X.509 / PKCS#12 key material
    r")$",
    re.IGNORECASE,
)
# The leading ".*\." on the env branch is mandatory, not optional: a bare
# basename "env" (virtualenv dirs, /usr/bin/env) must stay accessible.
# The ".+\." on the suffix branch likewise requires a non-empty stem.

_GLOB_WILDCARD_RE = re.compile(r"[*?]+")

# Shell metacharacters used to split a Bash command into path-like tokens.
_BASH_TOKEN_SPLIT_RE = re.compile(r"""[\s'"();|&<>=`,]+""")


def _credential_hit(path: str) -> str | None:
    """Return the credential token a path touches, or None.

    Both the literal path and its realpath are checked: the read-family tools
    follow symlinks, so a link planted in an allowed directory
    (ln -s /root/dqiii8/.env notes.txt) must not launder credential content.
    The literal path is still checked as a fallback for broken/dangling links,
    where realpath() cannot resolve the target.
    """
    if not path:
        return None
    candidates = {os.path.normpath(path)}
    try:
        candidates.add(os.path.realpath(path))
    except OSError as _re:  # pragma: no cover — realpath rarely raises
        log.warning("permission_analyzer: realpath failed for %r: %s", path, _re)

    for cand in sorted(candidates):
        parts = [p for p in cand.split(os.sep) if p]
        if not parts:
            continue
        # Whole path, not just ancestors: a Grep/Glob target may itself be the
        # credential directory (path="/root/.ssh").
        seg_hit = CREDENTIAL_DIRS.intersection(parts)
        if seg_hit:
            return sorted(seg_hit)[0]
        base = parts[-1]
        if _CREDENTIAL_TEMPLATE_RE.search(base):
            continue
        if _CREDENTIAL_BASENAME_RE.match(base):
            return base
    return None


def _glob_filter_hit(spec: str) -> str | None:
    """Return the credential token a Grep --glob filter targets, or None.

    The filter is a name pattern rather than a path, so wildcards are collapsed
    before matching: '**/.env*' -> '.env', '*.pem' -> '.pem'. A non-targeting
    filter collapses to something harmless ('*' -> '', '**/*.py' -> '.py'), so
    ordinary filtered greps are unaffected. Without this, a Grep rooted at an
    allowed directory could still funnel credential content back via the filter.
    """
    if not spec:
        return None
    base = spec.replace("\\", "/").rsplit("/", 1)[-1]
    collapsed = _GLOB_WILDCARD_RE.sub("", base)
    if not collapsed or collapsed == ".":
        return None
    if _CREDENTIAL_TEMPLATE_RE.search(collapsed):
        return None
    # "x" + collapsed supplies the stem that a suffix-only filter ('*.pem')
    # loses when its wildcard is removed.
    for probe in (collapsed, "x" + collapsed):
        if _CREDENTIAL_BASENAME_RE.match(probe):
            return collapsed
    return None

# Bash operators that indicate a WRITE to a file
_BASH_WRITE_SIGNS = [">", ">>", "tee ", "sed -i", "truncate "]

# Always CRITICAL regardless of mode
CRITICAL_PATTERNS = [
    r"rm\s+-rf\s+/\s*$",  # rm -rf / (exact root filesystem wipe)
    r"rm\s+-rf\s+/\s+",  # rm -rf / followed by space (flags or paths after /)
    r">\s+/dev/sda",  # write directly to disk device
    r"\bmkfs\b",  # format a filesystem
    r"\bdd\b.*\bif=",  # disk dump (potential disk wipe)
    r":\(\)\s*\{.*:\|:.*\}",  # fork bomb
]

HIGH_RISK_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf /anything (non-root paths)
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\$HOME",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM\s+agent_actions\b(?!\s+WHERE)",  # mass-delete without WHERE
    r"DROP\s+DATABASE",
    r"chmod\s+777\s+/",
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
    "plugins/cache/",
]

# Project directories always safe for writing
SAFE_PROJECT_DIRS = [
    str(DQIII8_ROOT) + "/",
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
        "System instructions cannot be modified from code. "
        "Use the revise-claude-md skill to generate a diff, "
        "then apply it manually from the terminal."
    ),
    "blocked_path:dqiii8.db": (
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


# In-process fallback counter for DENY/ESCALATE when DB is unavailable
_proc_rejection_counts: dict[str, int] = {}
_proc_rejection_lock = _threading.Lock()


class PermissionAnalyzer:
    """Centralized permission evaluator for Claude Code tools."""

    def _rm_target_is_allowed(self, cmd: str) -> bool:
        """
        True only if EVERY rm argument is an allowed-deletion target.
        The allowed token must be the final path component — not a substring
        anywhere in the command string.
        """
        allowed = set()
        for tok in ALLOWED_DELETIONS:
            t = tok.strip().strip("/").lstrip("./").replace("*", "")
            t = t.rsplit("/", 1)[-1]
            if t:
                allowed.add(t)

        targets: list[str] = []
        for m in re.finditer(r'\brm\b((?:\s+-{1,2}[a-zA-Z]+)*)((?:\s+[^\s;&|]+)+)', cmd):
            arg_blob = m.group(2)
            for arg in arg_blob.split():
                if arg.startswith("-"):
                    continue
                if arg in ("{}", "+", "\\;", ";"):
                    continue
                targets.append(arg)

        if not targets:
            return False

        for tgt in targets:
            # Absolute paths are only safe if they resolve inside a project dir
            if tgt.startswith("/"):
                real_tgt = os.path.realpath(os.path.normpath(tgt))
                if not any(real_tgt.startswith(os.path.realpath(safe)) for safe in SAFE_PROJECT_DIRS):
                    return False
            last = tgt.rstrip("/").rsplit("/", 1)[-1].replace("*", "")
            if last not in allowed:
                return False
        return True

    def _bash_touches_blocked(self, cmd: str) -> dict | None:
        """Block Bash commands that read credential paths or write to any blocked path."""
        # 1. Credential paths — block any access (read or write) using path-component matching
        for cred in BASH_CREDENTIAL_PATHS:
            # Match as path component: must be preceded/followed by space, quote, slash, or string boundary
            pattern = r'(?:^|[\s\'">/=@:(`$])' + re.escape(cred) + r'(?:[\s\'"/=@:;|)(&<>`$]|$)'
            if re.search(pattern, cmd):
                return self._deny(
                    "Bash", cmd,
                    f"Credential path '{cred}' referenced in Bash — access blocked.",
                    "CRITICAL",
                    f"bash_credential_path:{cred}",
                    "Use os.environ.get() for secrets. Never reference credential files in Bash.",
                )
        # 1b. Widened credential match (v3.3). The literal loop above needs a
        # boundary character immediately before the token, so 'cat prod.env',
        # 'cat config/app.env' and 'base64 certs/server.pem' slipped through.
        # Tokenize and reuse the same matcher the read family uses, so Bash and
        # Read/Grep/Glob cannot disagree about what counts as a credential.
        for tok in _BASH_TOKEN_SPLIT_RE.split(cmd):
            tok = tok.strip().strip("'\"")
            if not tok or tok.startswith("-"):
                continue
            hit = _credential_hit(tok)
            if hit:
                return self._deny(
                    "Bash", cmd,
                    f"Credential path '{tok}' referenced in Bash — access blocked ('{hit}').",
                    "CRITICAL",
                    f"bash_credential_path:{hit}",
                    "Use os.environ.get() for secrets. Never reference credential files in Bash.",
                )
        # 2. All BLOCKED_PATHS — block write operations
        is_write = any(sign in cmd for sign in _BASH_WRITE_SIGNS)
        if not is_write:
            # Detect sqlite3/psql/mysql with DML (writes to DB without shell write operators)
            if re.search(r'\b(?:sqlite3|psql|mysql|mariadb)\b', cmd):
                if re.search(r'\b(?:INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE)\b', cmd, re.IGNORECASE):
                    is_write = True
        if not is_write:
            # Detect python/perl writing inline
            cmd_lower = cmd.lower()
            if ("python" in cmd_lower or "perl" in cmd_lower) and "open(" in cmd:
                is_write = any(q in cmd for q in ("'w'", '"w"', "'a'", '"a"'))
        if is_write:
            for blocked in BLOCKED_PATHS:
                if blocked in cmd:
                    return self._deny(
                        "Bash", cmd,
                        f"Blocked path '{blocked}' targeted by Bash write operation.",
                        "CRITICAL",
                        f"bash_write_blocked_path:{blocked}",
                        "Use Write/Edit tool for file modifications. Bash cannot bypass path restrictions.",
                    )
        return None

    def _read_touches_credential(self, tool: str, path: str) -> dict | None:
        """Block a read-family tool from touching genuine credential material."""
        hit = _credential_hit(path)
        if not hit:
            return None
        return self._deny(
            tool,
            path,
            f"{tool} blocked at '{path}': credential material ('{hit}').",
            "CRITICAL",
            f"read_credential_path:{hit}",
            "Use os.environ.get() for secrets. Credential files are never read into context.",
        )

    def _read_family_credential_block(self, tool: str, inp: dict) -> dict | None:
        """Credential gate for Read / Grep / Glob (v3.3).

        Read — file_path.
        Grep — path (a file, a directory, or omitted meaning cwd) *and* the
               --glob filter. Grep returns file content, and even in
               files_with_matches mode it is a per-regex oracle over that
               content, so both routes to a credential file must be closed.
        Glob — path only. Glob returns file names, never content; gating the
               search root stops enumeration inside .ssh/.secrets/.gnupg, which
               is the part with recon value, while leaving a codebase-wide
               '**/*.pem' sweep (itself a legitimate audit action) alone.
        """
        path = inp.get("file_path") or inp.get("path") or ""
        blocked = self._read_touches_credential(tool, path)
        if blocked:
            return blocked
        if tool == "Grep":
            hit = _glob_filter_hit(inp.get("glob") or "")
            if hit:
                return self._deny(
                    tool,
                    str(inp.get("glob", "")),
                    f"Grep blocked: --glob filter targets credential files ('{hit}').",
                    "CRITICAL",
                    f"read_credential_path:{hit}",
                    "Narrow the glob to non-credential files. Secrets come from os.environ.get().",
                )
        return None

    def evaluate(self, tool: str, inp: dict, session_id: str | None = None) -> dict:
        """
        Evaluates whether a tool can execute.
        decision ∈ {APPROVE, DENY, ESCALATE}

        session_id: Hook event session ID (takes priority over environment variable).
        """
        _session = session_id or SESSION_ID
        # Grep/Glob carry their target in "path", not "file_path"/"command";
        # without it every Grep in a session would share the empty detail string
        # and trip _check_repeat_rejections against each other.
        detail = str(
            inp.get("file_path") or inp.get("command") or inp.get("path") or ""
        )

        # 0a. Safe project directories — fast-path (respects BLOCKED_PATHS)
        # Path is canonicalized (realpath + normpath) BEFORE the prefix check so
        # traversal payloads like /root/dqiii8/../../etc/sudoers cannot pass.
        if tool in ("Write", "Edit", "MultiEdit"):
            file_path = inp.get("file_path", inp.get("path", ""))
            real_path = os.path.realpath(os.path.normpath(file_path))
            in_safe_dir = any(
                real_path.startswith(os.path.realpath(safe))
                for safe in SAFE_PROJECT_DIRS
            )
            if in_safe_dir:
                if not any(blocked in real_path for blocked in BLOCKED_PATHS):
                    return self._approve(
                        "Safe project directory", "LOW", "safe_project_dir"
                    )

        # 0b block removed — learned_approvals moved after CRITICAL_PATTERNS (see 4a)

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

        # Extract Bash command once for all Bash checks (3c, 4, 4b)
        _bash_cmd = inp.get("command", "") or "" if tool == "Bash" else ""

        # 3c. BLOCKED_PATHS enforcement for Bash
        if tool == "Bash":
            try:
                cmd = _bash_cmd
                _bash_block = self._bash_touches_blocked(cmd)
                if _bash_block:
                    return _bash_block
            except Exception as _bte:
                log.warning("permission_analyzer: _bash_touches_blocked failed: %s", _bte)

        # 3d. Credential enforcement for the read family (mirror of 3c for Bash).
        # Must run before 4a (learned_approvals) so a historically-seen path
        # can never whitelist a credential read.
        if tool in ("Read", "Grep", "Glob"):
            try:
                _read_block = self._read_family_credential_block(tool, inp)
                if _read_block:
                    return _read_block
            except Exception as _rte:
                log.warning("permission_analyzer: _read_family_credential_block failed: %s", _rte)

        # 4. Always-CRITICAL commands (no mode exception, no ALLOWED_DELETIONS)
        if tool == "Bash":
            try:
                cmd = _bash_cmd
                for pattern in CRITICAL_PATTERNS:
                    if re.search(pattern, cmd, re.IGNORECASE):
                        return self._deny(
                            tool, cmd,
                            f"Catastrophic command blocked: '{cmd[:80]}'",
                            "CRITICAL", f"critical_pattern:{pattern}",
                            "This command is irreversible and catastrophic.",
                        )
            except Exception as _ce:
                log.warning("permission_analyzer: CRITICAL pattern check failed: %s", _ce)
                return self._deny(
                    tool, str(inp.get("command", ""))[:80],
                    "Internal analyzer error during critical check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry with a valid command string.",
                )

        # 4a. learned_approvals — only AFTER blocked-path + CRITICAL checks.
        # A historically-safe pattern can never override a CRITICAL deny.
        if self._is_learned_safe(tool, detail):
            return self._approve(
                "Pattern approved by history", "LOW", "learned_approval"
            )

        # 4b. High-risk commands with ALLOWED_DELETIONS exception
        if tool == "Bash":
            try:
                cmd = _bash_cmd
                for pattern in HIGH_RISK_PATTERNS:
                    if re.search(pattern, cmd, re.IGNORECASE):
                        is_safe_deletion = self._rm_target_is_allowed(cmd)
                        if is_safe_deletion:
                            break
                        if DQIII8_MODE == "autonomous":
                            return self._deny(
                                tool, cmd,
                                f"High-risk command in autonomous mode: {cmd[:80]}",
                                "HIGH", f"high_risk_pattern:{pattern}",
                                "Use ALLOWED_DELETIONS or run in supervised mode.",
                            )
                        else:
                            return self._deny(
                                tool, cmd,
                                f"Blocked command: '{cmd[:80]}'",
                                "CRITICAL", f"high_risk_pattern:{pattern}",
                                "This command is destructive and irreversible.",
                            )
            except Exception as _he:
                log.warning("permission_analyzer: HIGH_RISK pattern check failed: %s", _he)

        # 5. Autonomous mode — auto-approve standard tools (after checks)
        if DQIII8_MODE == "autonomous" and tool in AUTO_APPROVE_TOOLS:
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

            count = row[0] if row else 0
            if count >= MAX_SAME_REJECTION:
                conn.close()
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
            conn.close()
            # Reset in-process fallback if DB is healthy
            _key = f"{tool}|{detail[:50]}"
            with _proc_rejection_lock:
                _proc_rejection_counts.pop(_key, None)
        except Exception as e:
            log.warning(
                "permission_analyzer: _check_repeat_rejections query failed "
                "— using in-process counter: %s", e
            )
            _key = f"{tool}|{detail[:50]}"
            with _proc_rejection_lock:
                _proc_rejection_counts[_key] = _proc_rejection_counts.get(_key, 0) + 1
                _count = _proc_rejection_counts[_key]
            if _count >= MAX_SAME_REJECTION:
                return {
                    "decision": "ESCALATE",
                    "reason": (
                        f"Action '{tool}: {detail[:60]}' rejected "
                        f"{_count} times (in-process counter — DB unavailable). "
                        "Requires human decision."
                    ),
                    "risk_level": "HIGH",
                    "rule_triggered": f"repeat_rejection_inproc:{_count}",
                    "suggested_fix": "DB unavailable. Human confirmation required.",
                }
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

    def _check_resource_claim(
        self, tool: str, path: str, session_id: str
    ) -> dict | None:
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
        except Exception as e:
            log.warning("permission_analyzer: _check_resource_claim query failed: %s", e, exc_info=True)
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
        except Exception as e:
            log.warning("permission_analyzer: _check_budget query failed: %s", e, exc_info=True)
        return None


# ── Standalone functions (used by pre_tool_use.py) ──────────────────────────


def _notify_telegram_activation(tool_name: str, pattern: str) -> None:
    """Fire-and-forget Telegram alert when a pattern auto-activates at times_seen=3."""
    try:
        import requests
        from dotenv import load_dotenv

        load_dotenv(str(DQIII8_ROOT / ".env"))
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
    except Exception as e:
        log.warning("permission_analyzer: _notify_telegram_activation send failed: %s", e, exc_info=True)  # never block the pipeline


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
        if (
            result.get("risk_level") == "LOW"
            and result.get("reason") != "learned_approval"
        ):
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
    except Exception as e:
        log.warning("permission_analyzer: record_decision DB write failed: %s", e, exc_info=True)


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
    except Exception as e:
        log.warning("permission_analyzer: record_rejection DB channel write failed: %s", e, exc_info=True)

    # Channel 2: JSON mailbox (append to array)
    try:
        reject_path = DQIII8_ROOT / "tasks" / "permission_rejection.json"
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
    except Exception as e:
        log.warning("permission_analyzer: record_rejection JSON mailbox write failed: %s", e, exc_info=True)
