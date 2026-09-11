#!/usr/bin/env python3
"""Fase B — task-boundary migration (see /root/.claude/plans/parsed-swinging-donut.md).

Applies, idempotently:
  1. pre_tool_use.py: capture agent_id, resolve model via bin/core/model_map.py
  2. stop.py: close agent_registry.end_time on SubagentStop
  3. dqiii8.db: ALTER TABLE additive columns + index

Run by hand, outside any agent session (these hook files are a blocked write
path for the agent's own tools). Safe to re-run: each patch is skipped if
already applied, and the SQL uses idempotent guards.

Usage: python3 bin/tools/apply_fase_b.py [--db PATH] [--hooks-dir PATH]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

PRE_TOOL_USE_PATCHES = [
    (
        'agent = data.get("agent_id", data.get("agent_name", ""))\n'
        '_worktree = ""\n'
        "if not agent or (\n"
        "    len(agent) == 17\n"
        '    and agent[0] == "a"\n'
        '    and all(c in "0123456789abcdef" for c in agent[1:])\n'
        "):\n",
        'agent = data.get("agent_id", data.get("agent_name", ""))\n'
        '_worktree = ""\n'
        "_agent_id = (\n"
        "    agent\n"
        "    if agent\n"
        "    and len(agent) == 17\n"
        '    and agent[0] == "a"\n'
        '    and all(c in "0123456789abcdef" for c in agent[1:])\n'
        '    else ""\n'
        ")\n"
        "if not agent or _agent_id:\n",
    ),
    (
        "                if _rrow:\n" "                    _cand = os.path.join(\n",
        "                if _rrow:\n"
        "                    _agent_id = _rrow[0] or _agent_id\n"
        "                    _cand = os.path.join(\n",
    ),
    (
        '                agent = _lookup.get("agent_type", "claude-sonnet-5")\n'
        '                _worktree = _lookup.get("worktree_path", "") or ""\n'
        "    except Exception as e:\n",
        '                agent = _lookup.get("agent_type", "claude-sonnet-5")\n'
        '                _worktree = _lookup.get("worktree_path", "") or ""\n'
        "                if not _agent_id:\n"
        '                    _agent_id = _lookup.get("agent_id", "") or _agent_id\n'
        "    except Exception as e:\n",
    ),
    (
        '    _DB = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")\n'
        '    _model = os.environ.get("DQIII8_MODEL", agent)\n'
        "    _tier = _model_tier(_model)\n"
        '    _cwd = str(data.get("cwd", "") or "")\n',
        '    _DB = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")\n'
        '    _cwd = str(data.get("cwd", "") or "")\n',
    ),
    (
        "    from core.action_log import resolve_project_safe, generate_request_id\n"
        "\n"
        "    _project = resolve_project_safe(session, cwd=_cwd)\n",
        "    from core.action_log import resolve_project_safe, generate_request_id\n"
        "    from core.model_map import resolve_model\n"
        "\n"
        "    _model = resolve_model(agent)\n"
        "    _tier = _model_tier(_model)\n"
        "    _project = resolve_project_safe(session, cwd=_cwd)\n",
    ),
    (
        '            "(session_id,agent_name,tool_used,file_path,action_type,start_time_ms,model_tier,model_used,project,worktree,tier,request_id) "\n'
        '            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",\n',
        '            "(session_id,agent_name,tool_used,file_path,action_type,start_time_ms,model_tier,model_used,project,worktree,tier,request_id,agent_id) "\n'
        '            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",\n',
    ),
    (
        "                _tier_text(_model),\n"
        "                _request_id,\n"
        "            ),\n"
        "        )\n"
        "        _conn.commit()\n",
        "                _tier_text(_model),\n"
        "                _request_id,\n"
        "                _agent_id or None,\n"
        "            ),\n"
        "        )\n"
        "        _conn.commit()\n",
    ),
]

STOP_PATCHES = [
    (
        'session = data.get("session_id", "unknown")\n'
        'ROOT_DIR = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))\n'
        'DB = ROOT_DIR / "database" / "dqiii8.db"\n'
        'LESSONS = ROOT_DIR / "tasks" / "lessons.md"\n'
        'PROJECTS = ROOT_DIR / "projects"\n'
        "NOW = datetime.now().isoformat()\n",
        'session = data.get("session_id", "unknown")\n'
        'ROOT_DIR = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))\n'
        'DB = ROOT_DIR / "database" / "dqiii8.db"\n'
        'LESSONS = ROOT_DIR / "tasks" / "lessons.md"\n'
        'PROJECTS = ROOT_DIR / "projects"\n'
        "NOW = datetime.now().isoformat()\n"
        "\n"
        "# Fase B (task boundary, /root/.claude/plans/parsed-swinging-donut.md): close\n"
        "# the agent_registry row on SubagentStop. Payload shape for this event is\n"
        "# unverified (no hook in this repo reads it today) — best-effort, never blocks\n"
        "# the rest of this script's Stop-event logic, which runs unchanged either way.\n"
        'if data.get("hook_event_name") == "SubagentStop":\n'
        '    _sa_agent_id = data.get("agent_id", "")\n'
        "    if _sa_agent_id:\n"
        "        try:\n"
        "            import sqlite3 as _sa_sqlite3\n"
        "\n"
        "            _sa_conn = _sa_sqlite3.connect(str(DB), timeout=5)\n"
        "            _sa_conn.execute(\n"
        '                "UPDATE agent_registry SET end_time=? WHERE agent_id=? AND end_time IS NULL",\n'
        "                (NOW, _sa_agent_id),\n"
        "            )\n"
        "            _sa_conn.commit()\n"
        "            _sa_conn.close()\n"
        "        except Exception as _sa_exc:\n"
        '            _log.warning("SubagentStop: agent_registry close failed: %s", _sa_exc)\n',
    ),
]


def apply_patches(path: Path, patches: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new in patches:
        if new in text:
            print(f"  [skip] already applied in {path.name}: {old[:50]!r}...")
            continue
        if old not in text:
            print(f"  [WARN] pattern not found in {path.name} (file changed?): {old[:50]!r}...")
            continue
        text = text.replace(old, new, 1)
        changed = True
        print(f"  [ok]   patched {path.name}: {old[:50]!r}...")
    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"  -> wrote {path}")
    else:
        print(f"  -> no changes needed for {path}")


def apply_db_migration(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        for stmt in (
            "ALTER TABLE agent_registry ADD COLUMN end_time TEXT",
            "ALTER TABLE agent_actions ADD COLUMN agent_id TEXT",
        ):
            try:
                conn.execute(stmt)
                print(f"  [ok]   {stmt}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"  [skip] already applied: {stmt}")
                else:
                    raise
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_actions_agent_id ON agent_actions(agent_id)"
        )
        print("  [ok]   CREATE INDEX IF NOT EXISTS idx_agent_actions_agent_id")
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT_DIR / "database" / "dqiii8.db"))
    ap.add_argument("--hooks-dir", default=str(ROOT_DIR / ".claude" / "hooks"))
    args = ap.parse_args()

    hooks_dir = Path(args.hooks_dir)
    db_path = Path(args.db)

    print("== pre_tool_use.py ==")
    apply_patches(hooks_dir / "pre_tool_use.py", PRE_TOOL_USE_PATCHES)
    print("== stop.py ==")
    apply_patches(hooks_dir / "stop.py", STOP_PATCHES)
    print("== dqiii8.db migration ==")
    apply_db_migration(db_path)
    print("== done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
