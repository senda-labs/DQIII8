#!/usr/bin/env python3
"""Security middleware for DQ Dashboard."""
import os
import secrets
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))


def get_or_create_dashboard_token() -> str:
    """Get existing token or generate a new one."""
    token_file = JARVIS / "database" / ".dashboard_token"

    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()

    token = secrets.token_urlsafe(32)
    token_file.write_text(token, encoding="utf-8")
    os.chmod(str(token_file), 0o600)
    return token


def verify_token(provided_token: str) -> bool:
    """Verify a provided token against the stored one."""
    real_token = get_or_create_dashboard_token()
    return secrets.compare_digest(provided_token, real_token)
