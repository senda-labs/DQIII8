#!/usr/bin/env python3
"""Read-only audit of required env vars for DQIII8. Never prints secret values."""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.environ.get("DQIII8_ROOT", "/root/dqiii8"), ".env"))
except ImportError:
    pass  # dotenv optional

REQUIRED = [
    "GROQ_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]
OPTIONAL = [
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    "PIXELLAB_API_KEY",
]

missing = []
print("DQIII8 environment check")
print("=" * 32)
for key in REQUIRED:
    present = bool(os.environ.get(key, "").strip())
    print(f"[{'OK ' if present else 'MISSING'}] {key}")
    if not present:
        missing.append(key)
for key in OPTIONAL:
    present = bool(os.environ.get(key, "").strip())
    print(f"[{'OK ' if present else '---'}] {key} (optional)")

anthropic = os.environ.get("ANTHROPIC_API_KEY", "")
if anthropic.strip():
    print("[WARN] ANTHROPIC_API_KEY is set — must be \"\" in subprocess env for OAuth")

if missing:
    print(f"\nFAIL: {len(missing)} required var(s) missing: {', '.join(missing)}")
    sys.exit(1)
print("\nPASS: all required env vars present")
sys.exit(0)
