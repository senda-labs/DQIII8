#!/usr/bin/env python3
"""Session handover — saves current session state to sessions/YYYY-MM-DD_session_N.md"""

import os
import pwd
import subprocess
import sys
from datetime import date
from pathlib import Path

DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = DQIII8_ROOT / "sessions"

OPERATOR_MAP = {
    "root": "Iker",
    "plglobal-isabel": "Isabel Vinagre",
    "plglobal-mario": "Mario Cabeza",
}


def current_operator() -> str:
    # 2026-09-12 fix: was keyed on CLAUDE_CONFIG_DIR, an env var nothing in
    # this deployment ever sets (checked live: absent from Mario's real tmux
    # session env) — every /handover run by Isabel or Mario silently
    # mislabeled the operator as "Iker". The real Linux user (pwd, not an
    # env var — can't be unset) is the reliable signal each operator's
    # process actually runs as.
    username = pwd.getpwuid(os.getuid()).pw_name
    return OPERATOR_MAP.get(username, username)


def run(cmd: str) -> str:
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=str(DQIII8_ROOT)
        )
        return (result.stdout + result.stderr).strip()
    except Exception as e:
        return f"ERROR: {e}"


def next_session_path() -> Path:
    SESSIONS_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    n = 1
    while True:
        path = SESSIONS_DIR / f"{today}_session_{n}.md"
        if not path.exists():
            return path
        n += 1


def main():
    tests = run("python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -3")
    services = run(
        "systemctl is-active dqiii8-bot dq-dashboard ollama 2>/dev/null || echo 'systemctl not available'"
    )

    today = date.today().isoformat()
    operator = current_operator()
    content = f"""# Session Handover — {today}

## Operador
{operator}

## Tests
{tests}

## Active services
{services}

## Next steps
(empty — to be filled by the session)
"""

    out_path = next_session_path()
    out_path.write_text(content, encoding="utf-8")
    print(f"Handover saved: {out_path}")
    print(content)


if __name__ == "__main__":
    main()
