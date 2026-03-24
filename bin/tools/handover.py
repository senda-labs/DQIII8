#!/usr/bin/env python3
"""Session handover — saves current session state to sessions/YYYY-MM-DD_session_N.md"""

import subprocess
import sys
from datetime import date
from pathlib import Path

DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = DQIII8_ROOT / "sessions"


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
    git_log = run("git log --oneline -5")
    git_status = run("git status --short")
    tests = run("python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -3")
    services = run(
        "systemctl is-active jarvis-bot dq-dashboard autoreporte ollama 2>/dev/null || echo 'systemctl not available'"
    )

    today = date.today().isoformat()
    content = f"""# Session Handover — {today}

## Last 5 commits
{git_log}

## Uncommitted changes
{git_status if git_status else "(none)"}

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
