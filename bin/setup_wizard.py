#!/usr/bin/env python3
"""
DQ Setup Wizard — Interactive first-run configuration.
Guides non-technical users through API key setup and tier selection.

Usage:
    dq --setup
    python3 bin/setup_wizard.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", Path.home() / "dqiii8"))
ENV_FILE = JARVIS_ROOT / ".env"
ENV_EXAMPLE = JARVIS_ROOT / ".env.example"

_PLACEHOLDER_GROQ = "gsk_YOUR_KEY_HERE"
_PLACEHOLDER_ANT = "sk-ant-YOUR_KEY_HERE"


def _mask(key: str) -> str:
    if len(key) < 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


def _parse_env(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            k, _, v = stripped.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(env_lines: list[str], updates: dict) -> str:
    """Merge updates into the existing lines, preserving comments and structure."""
    written = set()
    output = []
    for line in env_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output.append(line)
            continue
        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        output.append(line)
    # Append any new keys not present in original file
    for key, val in updates.items():
        if key not in written:
            output.append(f"{key}={val}")
    return "\n".join(output) + "\n"


def setup() -> int:
    print("\n═══ DQ Setup Wizard ═══\n")

    # ── Ensure .env exists and is writable ───────────────────────────────────
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print("  ✓ Created .env from .env.example")
        else:
            ENV_FILE.touch()
            print("  ✓ Created empty .env")

    os.chmod(ENV_FILE, 0o600)

    raw = ENV_FILE.read_text(encoding="utf-8")
    env_lines = raw.splitlines()
    existing = _parse_env(raw)
    updates: dict[str, str] = {}

    print("  This wizard configures your API keys and default tier.\n")

    # ── Step 1: Groq (free) ──────────────────────────────────────────────────
    print("─── Step 1: Groq API Key (FREE — recommended) ───")
    print("  Get yours at: https://console.groq.com/keys")
    print("  Enables Tier B: fast, free cloud models.\n")

    current_groq = existing.get("GROQ_API_KEY", "")
    if current_groq and current_groq not in ("", _PLACEHOLDER_GROQ):
        print(f"  Current: {_mask(current_groq)}")
        if input("  Change it? (y/N): ").strip().lower() == "y":
            val = input("  Paste your Groq API key: ").strip()
            if val:
                updates["GROQ_API_KEY"] = val
                print("  ✓ Groq key saved.\n")
            else:
                print("  ⚠ No input — keeping current key.\n")
        else:
            print("  ✓ Keeping current Groq key.\n")
    else:
        val = input("  Paste your Groq API key (or Enter to skip): ").strip()
        if val:
            updates["GROQ_API_KEY"] = val
            print("  ✓ Groq key saved.\n")
        else:
            print("  ⚠ Skipped. Only Tier C (local) will be available.\n")

    # ── Step 2: Anthropic (paid, optional) ───────────────────────────────────
    print("─── Step 2: Anthropic API Key (PAID — optional) ───")
    print("  Get yours at: https://console.anthropic.com/settings/keys")
    print("  Enables Tier A/S/S+: Claude Sonnet and Opus.\n")

    current_ant = existing.get("ANTHROPIC_API_KEY", "")
    if current_ant and current_ant not in ("", _PLACEHOLDER_ANT):
        print(f"  Current: {_mask(current_ant)}")
        if input("  Change it? (y/N): ").strip().lower() == "y":
            val = input("  Paste your Anthropic API key: ").strip()
            if val:
                updates["ANTHROPIC_API_KEY"] = val
                print("  ✓ Anthropic key saved.\n")
            else:
                print("  ⚠ No input — keeping current key.\n")
        else:
            print("  ✓ Keeping current Anthropic key.\n")
    else:
        val = input("  Paste your Anthropic API key (or Enter to skip): ").strip()
        if val:
            updates["ANTHROPIC_API_KEY"] = val
            print("  ✓ Anthropic key saved.\n")
        else:
            print("  ⚠ Skipped. Tiers A/S/S+ won't be available.\n")

    # ── Step 3: Telegram (optional) ──────────────────────────────────────────
    print("─── Step 3: Telegram Notifications (optional) ───")
    if input("  Set up Telegram notifications? (y/N): ").strip().lower() == "y":
        bot_token = input("  Telegram Bot Token: ").strip()
        chat_id = input("  Telegram Chat ID: ").strip()
        if bot_token:
            updates["TELEGRAM_BOT_TOKEN"] = bot_token
        if chat_id:
            updates["TELEGRAM_CHAT_ID"] = chat_id
        if bot_token and chat_id:
            print("  ✓ Telegram configured.\n")
        else:
            print("  ⚠ Incomplete — notifications not fully configured.\n")
    else:
        print("  ⚠ Skipped.\n")

    # ── Step 4: Default tier ──────────────────────────────────────────────────
    print("─── Step 4: Default Tier ───")
    print("  Choose how DQ routes tasks by default:\n")
    print("  1) auto          — DQ decides the best tier per task (recommended)")
    print("  2) groq-only     — Groq handles everything (fast, free, requires Step 1)")
    print("  3) groq+ollama   — Groq plans, Ollama runs code (free, private)")
    print("  4) ollama-only   — Everything local, no internet (slowest)\n")

    choice = input("  Your choice (1/2/3/4) [1]: ").strip()
    tier_map = {"1": "auto", "2": "groq-only", "3": "groq+ollama", "4": "ollama-only"}
    tier_config = tier_map.get(choice, "auto")
    updates["DQ_DEFAULT_TIER"] = tier_config
    print(f"  ✓ Default tier: {tier_config}\n")

    # ── Write .env ────────────────────────────────────────────────────────────
    if updates:
        new_content = _write_env(env_lines, updates)
        ENV_FILE.write_text(new_content, encoding="utf-8")
        os.chmod(ENV_FILE, 0o600)

    # ── Summary ───────────────────────────────────────────────────────────────
    final_env = _parse_env(ENV_FILE.read_text(encoding="utf-8"))

    tiers = ["Tier C (Ollama, local, $0)"]
    groq_key = final_env.get("GROQ_API_KEY", "")
    ant_key = final_env.get("ANTHROPIC_API_KEY", "")
    if groq_key and groq_key != _PLACEHOLDER_GROQ:
        tiers.append("Tier B (Groq, free)")
    if ant_key and ant_key != _PLACEHOLDER_ANT:
        tiers.append("Tier A/S/S+ (Claude, paid)")

    print("═══ Setup Complete ═══")
    print(f"  Config:    {ENV_FILE}")
    print(f"  Tier mode: {tier_config}")
    print(f"  Available: {', '.join(tiers)}")
    print()
    print("  Try it now:")
    print('    dq "Explain what Value at Risk means in 3 sentences"')
    print()

    # ── Dashboard offer ───────────────────────────────────────────────────────
    print("─── Dashboard ───")
    if input("  Open web dashboard now? (Y/n): ").strip().lower() not in ("n", "no"):
        subprocess.Popen(
            [sys.executable, str(JARVIS_ROOT / "bin" / "dashboard.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  Dashboard started at http://localhost:8080")
        print("  Stop it with: pkill -f dashboard.py")
    else:
        print("  Start later with: dq --dashboard")
    print()

    return 0


def main() -> None:
    try:
        sys.exit(setup())
    except KeyboardInterrupt:
        print("\n\n  ⚠ Setup cancelled. Run 'dq --setup' to try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
