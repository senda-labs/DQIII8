"""
JAL Common Utilities
====================
Shared helpers for jal_planner, jal_run, jal_scoring, jal_critic.
"""

import os
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))


def load_env():
    """Load .env file into os.environ (setdefault — does not overwrite existing)."""
    env = JARVIS / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
