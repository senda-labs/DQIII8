#!/usr/bin/env python3
"""
DQIII8 Hook — PostToolUse
Patch 5: SQLite block in try/except — never blocks real work
Auto-format Python with Black after each edit.
"""

import sys, json, time, os, subprocess

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
inp = data.get("tool_input", {})
resp = data.get("tool_response", {}) or {}
session = data.get("session_id", "unknown")
agent = data.get("agent_id", data.get("agent_name", ""))
if not agent:
    try:
        with open(f"/tmp/jarvis_agent_{session}.json", encoding="utf-8") as _af:
            agent = json.load(_af).get("agent_type", "claude-sonnet-4-6")
    except Exception:
        agent = "claude-sonnet-4-6"
# Infer from tool+path if agent looks like a UUID (17 hex chars starting with 'a')
if len(agent) == 17 and agent[0] == "a" and all(c in "0123456789abcdef" for c in agent[1:]):
    _fp = inp.get("file_path", inp.get("command", ""))
    if tool in ("Edit", "Write", "MultiEdit") and _fp.endswith(".py"):
        agent = "python-specialist"
    elif tool == "Bash" and any(
        k in _fp for k in ("git commit", "git push", "git branch", "git tag")
    ):
        agent = "git-specialist"
    else:
        agent = "claude-sonnet-4-6"
now_ms = int(time.time() * 1000)

# ── Auto-format Python ──────────────────────────────────────────────
if tool in ("Edit", "Write", "MultiEdit"):
    path = inp.get("file_path", inp.get("path", ""))
    if path and path.endswith(".py"):
        try:
            subprocess.run(["black", "--quiet", path], capture_output=True, timeout=10)
        except Exception:
            pass

# ── Patch 5: metrics in try/except — never block real work ──
try:
    _bin = os.path.join(os.environ.get("DQIII8_ROOT", "/root/jarvis"), "bin")
    if _bin not in sys.path:
        sys.path.insert(0, _bin)
    from db import get_db as _get_db, DB_PATH as _DB_PATH

    if _DB_PATH.exists():
        # Detect failure via exit_code (Bash) OR type/is_error/error (other tools)
        _exit_code = resp.get("exit_code")
        if _exit_code is not None:
            success = 1 if _exit_code == 0 else 0
        else:
            success = (
                0
                if (resp.get("type") == "error" or resp.get("is_error") or resp.get("error"))
                else 1
            )
        error_msg = (resp.get("stderr") or resp.get("error") or "")[:500]
        # ── False-positive filter: JSON stdout misclassified as error ──────────
        # ctx_execute / context-mode MCP tools write {"stdout":"..."} JSON output
        # which can end up in stderr/error fields — that's output, not an error.
        # Also suppress "sin stderr" entries where stdout contains JSON output.
        if not success:
            _raw_out = resp.get("stdout") or ""
            _looks_json = error_msg.lstrip().startswith('{"stdout"') or (
                not error_msg
                and isinstance(_raw_out, str)
                and _raw_out.lstrip().startswith('{"stdout"')
            )
            if _looks_json:
                success = 1
                error_msg = ""
        content = inp.get("new_content", inp.get("content", ""))
        bytes_wr = len(content.encode("utf-8", errors="replace")) if content else 0
        # When failing without stderr: log tool + generic reason for audit
        stored_error = error_msg or (f"{tool} failed (no stderr)" if not success else None)

        with _get_db(timeout=2) as conn:
            # Find the open action row first (to get its id for error_log FK)
            _action_row = conn.execute(
                "SELECT id FROM agent_actions "
                "WHERE session_id=? AND tool_used=? AND end_time_ms IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (session, tool),
            ).fetchone()
            _action_id = _action_row[0] if _action_row else None

            # Close the open action from pre_tool_use
            if _action_id:
                conn.execute(
                    "UPDATE agent_actions "
                    "SET end_time_ms=?, duration_ms=?-COALESCE(start_time_ms,?), "
                    "    success=?, error_message=?, bytes_written=? "
                    "WHERE id=?",
                    (now_ms, now_ms, now_ms, success, stored_error, bytes_wr, _action_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE agent_actions
                    SET end_time_ms=?, duration_ms=?-COALESCE(start_time_ms,?),
                        success=?, error_message=?, bytes_written=?
                    WHERE id=(
                        SELECT id FROM agent_actions
                        WHERE session_id=? AND tool_used=? AND end_time_ms IS NULL
                        ORDER BY id DESC LIMIT 1)
                """,
                    (now_ms, now_ms, now_ms, success, stored_error, bytes_wr, session, tool),
                )

            if not success:
                try:
                    conn.execute(
                        "INSERT INTO error_log "
                        "(timestamp, session_id, agent_name, error_type, error_message, keywords, resolved, action_id) "
                        "VALUES (datetime('now'), ?, ?, ?, ?, ?, 0, ?)",
                        (
                            session,
                            agent,
                            f"{tool}Error",
                            stored_error or f"{tool} failed",
                            json.dumps([agent, tool]),
                            _action_id,
                        ),
                    )
                except Exception as _el_err:
                    print(f"[post_tool_use] error_log INSERT failed: {_el_err}", file=sys.stderr)
except Exception:
    pass  # logging fails silently

# ── Implicit correction capture ──────────────────────────────────────
# Pattern: tool fails → same agent+file → tool succeeds = silent fix → lesson
try:
    import sqlite3 as _ics

    _PENDING = f"/tmp/jarvis_pending_{session[:8]}.json"
    _fpath = inp.get("file_path", inp.get("path", ""))
    _exit_c = resp.get("exit_code")
    _ok = (
        (_exit_c == 0)
        if _exit_c is not None
        else not (resp.get("type") == "error" or resp.get("is_error") or resp.get("error"))
    )
    _err = (resp.get("stderr") or resp.get("error") or "")[:200]
    _pend: dict = {}
    if os.path.exists(_PENDING):
        try:
            with open(_PENDING, encoding="utf-8") as _f:
                _pend = json.load(_f)
        except Exception:
            _pend = {}
    _key = f"{agent}|{_fpath}" if _fpath else ""
    if _key:
        if not _ok:
            _pend[_key] = {"error_type": f"{tool}Error", "error_msg": _err or f"{tool} failed"}
            with open(_PENDING, "w", encoding="utf-8") as _f:
                json.dump(_pend, _f)
        elif _key in _pend:
            _fail = _pend.pop(_key)
            with open(_PENDING, "w", encoding="utf-8") as _f:
                json.dump(_pend, _f)
            _db_path = os.path.join(
                os.environ.get("DQIII8_ROOT", "/root/jarvis"), "database", "dqiii8.db"
            )
            if os.path.exists(_db_path):
                _vc = _ics.connect(_db_path, timeout=2)
                _proj = os.environ.get("JARVIS_PROJECT", "jarvis-core")
                _vc.execute(
                    "INSERT INTO vault_memory"
                    " (subject,predicate,object,project,confidence,entry_type,source,created_at,last_seen)"
                    " VALUES (?,?,?,?,0.6,'lesson','post_tool_use',datetime('now'),datetime('now'))"
                    " ON CONFLICT(subject,predicate,object) DO UPDATE SET"
                    "   times_seen=times_seen+1, last_seen=datetime('now')",
                    (
                        _fail["error_type"],
                        "resolved_by",
                        f"{tool} on {os.path.basename(_fpath)}",
                        _proj,
                    ),
                )
                _vc.commit()
                _vc.close()
                # Mark matching error_log entry as resolved (separate connection so vault commit is safe)
                try:
                    _vc2 = _ics.connect(_db_path, timeout=2)
                    _vc2.execute(
                        "UPDATE error_log SET resolved=1, resolution=?"
                        " WHERE id=(SELECT id FROM error_log"
                        "  WHERE session_id=? AND error_type=? AND resolved=0"
                        "  ORDER BY id DESC LIMIT 1)",
                        (
                            f"auto-fixed by {tool} on {os.path.basename(_fpath)}",
                            session,
                            _fail["error_type"],
                        ),
                    )
                    _vc2.commit()
                    _vc2.close()
                except Exception:
                    pass
except Exception:
    pass

sys.exit(0)
