#!/usr/bin/env python3
"""Database security utilities for DQIII8."""
import sqlite3
import os
import re
import stat
import subprocess
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS / "database" / "jarvis_metrics.db"


def secure_db_permissions():
    """Set database file to owner-only read/write (chmod 600)."""
    if DB_PATH.exists():
        os.chmod(DB_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 600
        for ext in ["-wal", "-shm"]:
            wal = Path(str(DB_PATH) + ext)
            if wal.exists():
                os.chmod(wal, stat.S_IRUSR | stat.S_IWUSR)
        print(f"DB permissions set to 600: {DB_PATH}")


def secure_env_permissions():
    """Set .env file to owner-only read (chmod 400)."""
    env_file = JARVIS / ".env"
    if env_file.exists():
        os.chmod(env_file, stat.S_IRUSR)  # 400 (read-only by owner)
        print(f".env permissions set to 400: {env_file}")


def verify_no_secrets_in_repo():
    """Scan tracked files for potential secrets."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, cwd=str(JARVIS)
    )
    files = result.stdout.strip().split("\n")

    secret_patterns = [
        r"ghp_[a-zA-Z0-9]{36}",           # GitHub PAT
        r"sk-ant-[a-zA-Z0-9-]{40,}",      # Anthropic key
        r"gsk_[a-zA-Z0-9]{20,}",          # Groq key
        r"sk-[a-zA-Z0-9]{20,}",           # OpenAI key
        r"xoxb-[a-zA-Z0-9-]+",            # Slack token
    ]

    issues = []
    for f in files:
        fpath = JARVIS / f
        if not fpath.exists() or fpath.suffix in (".pyc", ".db", ".json", ".lock"):
            continue
        try:
            content = fpath.read_text(errors="ignore")
            for pattern in secret_patterns:
                if re.search(pattern, content):
                    issues.append(
                        f"ALERT: {f} contains potential secret matching {pattern[:20]}..."
                    )
        except Exception:
            pass

    if issues:
        print("  SECRETS FOUND IN TRACKED FILES:")
        for i in issues:
            print(f"  {i}")
        return False
    else:
        print("  No secrets found in tracked files")
        return True


if __name__ == "__main__":
    secure_db_permissions()
    secure_env_permissions()
    verify_no_secrets_in_repo()
