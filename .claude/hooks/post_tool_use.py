#!/usr/bin/env python3
"""
DQIII8 Hook — PostToolUse
Patch 5: SQLite block in try/except — never blocks real work
Auto-format Python with Black after each edit.
"""

import json
import logging
import logging.handlers
import os
import subprocess
import sys
import time
from pathlib import Path

_log = logging.getLogger("dqiii8.post_tool_use")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _log_dir = Path("/var/log/dqiii8")
    if _log_dir.exists():
        _fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "hooks.log"), maxBytes=2_000_000, backupCount=3
        )
        _fh.setFormatter(logging.Formatter("%(asctime)s [post_tool_use] %(levelname)s %(message)s"))
        _log.addHandler(_fh)
    else:
        _log.addHandler(logging.NullHandler())

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
inp = data.get("tool_input", {})
resp = data.get("tool_response", {}) or {}
session = data.get("session_id", "unknown")
_dqiii8_root_path = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
agent = data.get("agent_id", data.get("agent_name", ""))
if not agent:
    # Stage 0 / Correction G: the lookup file subagent_start.py writes is keyed
    # by agent_id, not session_id — resolve session_id -> agent_id via
    # agent_registry first, then build the correct filename. Try a direct
    # session-keyed match first too (harmless, cheap, covers any future case
    # where session_id and agent_id happen to coincide).
    agent = "claude-sonnet-5"
    try:
        _direct = _dqiii8_root_path / "tmp" / f"dqiii8_agent_{session}.json"
        if _direct.exists():
            with open(_direct, encoding="utf-8") as _af:
                agent = json.load(_af).get("agent_type", "claude-sonnet-5")
        else:
            import sqlite3 as _rics

            _reg_db = _dqiii8_root_path / "database" / "dqiii8.db"
            _resolved_agent_id = None
            if _reg_db.exists():
                _rconn = _rics.connect(str(_reg_db), timeout=2)
                _rrow = _rconn.execute(
                    "SELECT agent_id FROM agent_registry WHERE parent_session=? "
                    "ORDER BY start_time DESC LIMIT 1",
                    (session,),
                ).fetchone()
                _rconn.close()
                _resolved_agent_id = _rrow[0] if _rrow else None
            if _resolved_agent_id:
                _lookup = _dqiii8_root_path / "tmp" / f"dqiii8_agent_{_resolved_agent_id}.json"
                if _lookup.exists():
                    with open(_lookup, encoding="utf-8") as _af:
                        agent = json.load(_af).get("agent_type", "claude-sonnet-5")
    except Exception as e:
        _log.debug("agent-file read skipped: %s", e)
# Infer from tool+path if agent looks like a UUID (17 hex chars starting with 'a')
if (
    len(agent) == 17
    and agent[0] == "a"
    and all(c in "0123456789abcdef" for c in agent[1:])
):
    _fp = inp.get("file_path", inp.get("command", ""))
    if tool in ("Edit", "Write", "MultiEdit") and _fp.endswith(".py"):
        agent = "python-specialist"
    elif tool == "Bash" and any(
        k in _fp for k in ("git commit", "git push", "git branch", "git tag")
    ):
        agent = "git-specialist"
    else:
        agent = "claude-sonnet-5"
now_ms = int(time.time() * 1000)

# ── Auto-format Python ──────────────────────────────────────────────
if tool in ("Edit", "Write", "MultiEdit"):
    path = inp.get("file_path", inp.get("path", ""))
    if path and path.endswith(".py"):
        try:
            subprocess.run(["black", "--quiet", path], capture_output=True, timeout=10)
        except Exception as e:
            _log.debug("black format skipped: %s", e)

# ── Patch 5 / Stage 0 (Correction A): metrics in try/except — never block real work ──
# sys.path must point at bin/core, where db.py actually lives (matches stop.py's
# convention since the bin/ reorg in 24129d7) — the old `bin/` insert made this
# `from db import ...` raise ModuleNotFoundError on every call since mid-June.
try:
    _bin_core = str(_dqiii8_root_path / "bin" / "core")
    if _bin_core not in sys.path:
        sys.path.insert(0, _bin_core)
except Exception as e:
    _log.error("metrics DB import path setup failed: %s", e, exc_info=True)

try:
    from db import get_db as _get_db, DB_PATH as _DB_PATH
except Exception as e:
    _log.error("metrics DB import failed (db.py not found on sys.path): %s", e, exc_info=True)
    _DB_PATH = None
    _get_db = None

try:
    if _get_db is not None and _DB_PATH is not None and _DB_PATH.exists():
        # Detect failure via exit_code (Bash) OR type/is_error/error (other tools)
        _exit_code = resp.get("exit_code")
        if _exit_code is not None:
            success = 1 if _exit_code == 0 else 0
        else:
            success = (
                0
                if (
                    resp.get("type") == "error"
                    or resp.get("is_error")
                    or resp.get("error")
                )
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
        stored_error = error_msg or (
            f"{tool} failed (no stderr)" if not success else None
        )
        _fp_match = inp.get("file_path", inp.get("command", ""))

        _action_id = None
        # Stage 0 / Correction H: raise the close-out timeout to match the INSERT
        # side (was timeout=2, tighter than pre_tool_use.py's timeout=10) — the
        # 2s connection was the second, independent SQLITE_BUSY loss source under
        # parallel dispatch, on top of the matching-key bug below.
        with _get_db(timeout=10) as conn:
            # Stage 0 / Correction H + I.2: match by (session_id, tool_used,
            # file_path) — not the old (session_id, tool_used) LIFO-only key,
            # which cross-attributes duration/success between concurrent
            # same-tool calls on different files/commands. file_path here is
            # never truncated (matches pre_tool_use.py's INSERT, also fixed to
            # stop truncating at [:120] — a truncated-vs-full mismatch would
            # silently defeat this exact match). Most-recent-open (id DESC)
            # within the narrowed key is the tie-break: any row left open by an
            # interrupted/rejected/crashed prior call must not be able to
            # silently absorb today's close-out and duration — that row stays
            # open (and is a Stage 6 B2-style reconciliation candidate) rather
            # than accumulating a permanent lag. No per-row tool_use_id column
            # exists yet (would require a schema migration outside this
            # stage's scope); this is a documented residual gap, not a full fix.
            _action_row = conn.execute(
                "SELECT id FROM agent_actions "
                "WHERE session_id=? AND tool_used=? AND file_path=? AND end_time_ms IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (session, tool, _fp_match),
            ).fetchone()
            _action_id = _action_row[0] if _action_row else None
            if _action_id is None:
                # Fallback: file_path mismatch (e.g. legacy row from before this
                # fix) — fall back to the old, looser (session, tool) LIFO match
                # rather than leaving the row permanently open.
                _action_row = conn.execute(
                    "SELECT id FROM agent_actions "
                    "WHERE session_id=? AND tool_used=? AND end_time_ms IS NULL "
                    "ORDER BY id DESC LIMIT 1",
                    (session, tool),
                ).fetchone()
                _action_id = _action_row[0] if _action_row else None

            if _action_id:
                conn.execute(
                    "UPDATE agent_actions "
                    "SET end_time_ms=?, duration_ms=?-COALESCE(start_time_ms,?), "
                    "    success=?, error_message=?, bytes_written=? "
                    "WHERE id=?",
                    (
                        now_ms,
                        now_ms,
                        now_ms,
                        success,
                        stored_error,
                        bytes_wr,
                        _action_id,
                    ),
                )

        # Separate transaction: error_log INSERT must not share a transaction with
        # agent_actions UPDATE — a failed INSERT caught inside the same with-block
        # lets get_db() commit the UPDATE without the INSERT, creating an orphaned
        # success=0 row with no error_log counterpart (audit component_2 = 0).
        if not success:
            try:
                with _get_db(timeout=10) as _el_conn:
                    _el_conn.execute(
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
                _log.warning(
                    "error_log INSERT failed — orphan created for action_id=%s: %s",
                    _action_id,
                    _el_err,
                    exc_info=True,
                )
except Exception as e:
    _log.warning("metrics DB update failed: %s", e, exc_info=True)

# ── Implicit correction capture ──────────────────────────────────────
# Pattern: tool fails → same agent+file → tool succeeds = silent fix → lesson
try:
    import sqlite3 as _ics

    _PENDING = f"/tmp/dqiii8_pending_{session[:8]}.json"
    _fpath = inp.get("file_path", inp.get("path", ""))
    _exit_c = resp.get("exit_code")
    _ok = (
        (_exit_c == 0)
        if _exit_c is not None
        else not (
            resp.get("type") == "error" or resp.get("is_error") or resp.get("error")
        )
    )
    _err = (resp.get("stderr") or resp.get("error") or "")[:200]
    _pend: dict = {}
    if os.path.exists(_PENDING):
        try:
            with open(_PENDING, encoding="utf-8") as _f:
                _pend = json.load(_f)
        except Exception as e:
            _log.debug("pending-file load skipped: %s", e)
            _pend = {}
    _key = f"{agent}|{_fpath}" if _fpath else ""
    if _key:
        if not _ok:
            _pend[_key] = {
                "error_type": f"{tool}Error",
                "error_msg": _err or f"{tool} failed",
            }
            with open(_PENDING, "w", encoding="utf-8") as _f:
                json.dump(_pend, _f)
        elif _key in _pend:
            _fail = _pend.pop(_key)
            with open(_PENDING, "w", encoding="utf-8") as _f:
                json.dump(_pend, _f)
            _db_path = os.path.join(
                os.environ.get("DQIII8_ROOT", "/root/dqiii8"), "database", "dqiii8.db"
            )
            if os.path.exists(_db_path):
                _vc = _ics.connect(_db_path, timeout=10)
                try:
                    _bin_root = str(_dqiii8_root_path / "bin")
                    if _bin_root not in sys.path:
                        sys.path.insert(0, _bin_root)
                    from core.action_log import resolve_project_safe as _rps

                    _proj = _rps(session, cwd=data.get("cwd")) or "dqiii8-core"
                except Exception:
                    _proj = "dqiii8-core"
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
                    _vc2 = _ics.connect(_db_path, timeout=10)
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
                except Exception as e:
                    _log.warning("error-log resolution failed: %s", e, exc_info=True)
except Exception as e:
    _log.warning("correction-capture failed: %s", e, exc_info=True)

# ── Large Output Detector: inject summarizer guidance when output is huge ─────
# PostToolUse cannot suppress the raw output, but injecting an additionalContext
# with a compact summary + summarize_output.py invocation hint lets Claude work
# from the summary rather than re-processing the large raw block.
try:
    _raw_resp = data.get("tool_response", "") or ""
    if isinstance(_raw_resp, dict):
        _raw_resp = _raw_resp.get("stdout", "") or str(_raw_resp)
    _resp_str = str(_raw_resp)
    _LARGE_THRESHOLD = 3000  # chars — ~750 tokens

    if len(_resp_str) > _LARGE_THRESHOLD and tool == "Bash":
        _head = _resp_str[:1500]
        _tail = _resp_str[-800:]
        _omitted = len(_resp_str) - 1500 - 800
        _token_est = round(_omitted / 4)
        _summary_ctx = (
            f"\n[PostToolUse — LARGE OUTPUT DETECTED: {len(_resp_str):,} chars]\n"
            f"Head (1500 chars):\n{_head}\n"
            f"{'─'*40}\n"
            f"[...{_omitted:,} chars / ~{_token_est:,} tokens omitidos...]\n"
            f"{'─'*40}\n"
            f"Tail (800 chars):\n{_tail}\n"
            f"\nPara analizar el contenido omitido:\n"
            f"  python3 bin/tools/summarize_output.py "
            f"--query \"¿Qué [error/dato] buscas?\" < /tmp/last_output.txt\n"
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": _summary_ctx,
            }
        }))
        sys.exit(0)
except Exception as e:
    _log.debug("large-output detector skipped: %s", e)

sys.exit(0)
