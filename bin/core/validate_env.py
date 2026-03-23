#!/usr/bin/env python3
"""Validates the DQIII8 environment at startup. Reports which tiers are available."""

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def check_tier_c():
    """Tier C: Ollama local."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "qwen2.5-coder" in result.stdout:
            return True, "qwen2.5-coder:7b detected"
        elif result.returncode == 0:
            return (
                False,
                "Ollama active but qwen2.5-coder not installed. Run: ollama pull qwen2.5-coder:7b",
            )
        return False, "Ollama not responding"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "Ollama not installed or not accessible"


def check_tier_b():
    """Tier B: Groq o OpenRouter free."""
    groq = os.environ.get("GROQ_API_KEY", "")
    openrouter = os.environ.get("OPENROUTER_API_KEY", "")
    if groq:
        return True, "GROQ_API_KEY configured"
    elif openrouter:
        return True, "OPENROUTER_API_KEY configured (fallback)"
    return False, "GROQ_API_KEY and OPENROUTER_API_KEY not defined. Tier B unavailable."


def check_tier_a():
    """Tier A: Claude API. Returns None when not needed for configured tier."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return True, "ANTHROPIC_API_KEY configured"
    tier_config = os.environ.get("DQ_DEFAULT_TIER", "auto")
    if tier_config in ("groq-only", "groq+ollama", "ollama-only"):
        return None, f"Tier A not configured (not needed for DQ_DEFAULT_TIER={tier_config})"
    return False, "ANTHROPIC_API_KEY not defined. Tier A unavailable. Run: dq --setup"


def check_db():
    """Verifica que la DB existe y es accesible."""
    root = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
    db_path = root / "database" / "dqiii8.db"
    if not db_path.exists():
        return False, f"DB not found at {db_path}"
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("SELECT 1")
        conn.close()
        return True, "dqiii8.db accessible"
    except Exception as e:
        return False, f"DB error: {e}"


def check_telegram():
    """Verifica Telegram bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return True, "Telegram configured"
    return (
        False,
        "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not defined. Notifications disabled.",
    )


def check_vps_health():
    """Basic VPS resource check."""
    # Disco
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024**3)
    pct_used = (used / total) * 100
    if pct_used > 85:
        print(f"  ⚠️  Disco: {pct_used:.0f}% usado ({free_gb:.1f}GB libres)")
    else:
        print(f"  ✓ Disco: {pct_used:.0f}% usado ({free_gb:.1f}GB libres)")

    # RAM
    with open("/proc/meminfo", encoding="utf-8") as f:
        meminfo = f.read()
    mem_available = (
        int([line for line in meminfo.split("\n") if "MemAvailable" in line][0].split()[1]) // 1024
    )
    if mem_available < 512:
        print(f"  ⚠️  RAM disponible: {mem_available}MB (< 512MB)")
    else:
        print(f"  ✓ RAM disponible: {mem_available}MB")

    # SQLite size
    root = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
    db_path = root / "database" / "dqiii8.db"
    if db_path.exists():
        db_size_mb = db_path.stat().st_size / (1024**2)
        if db_size_mb > 100:
            print(f"  ⚠️  DB size: {db_size_mb:.0f}MB (considerar VACUUM)")
        else:
            print(f"  ✓ DB size: {db_size_mb:.1f}MB")


def main():
    import argparse as _ap
    _parser = _ap.ArgumentParser(add_help=False)
    _parser.add_argument("--quiet", action="store_true",
                         help="Suppress all output except critical errors")
    _parser.add_argument("--verbose", action="store_true")
    _args, _ = _parser.parse_known_args()
    quiet = _args.quiet and not _args.verbose

    def _print(*a, **kw):
        if not quiet:
            print(*a, **kw)

    checks = [
        ("Tier C (local, $0)", check_tier_c),
        ("Tier B (cloud free)", check_tier_b),
        ("Tier A (cloud paid)", check_tier_a),
        ("Database", check_db),
        ("Telegram", check_telegram),
    ]

    all_ok = True
    available_tiers = []

    _print("─── DQIII8 Environment Check ───")
    for name, check_fn in checks:
        ok, msg = check_fn()
        if ok is None:
            _print(f"  ℹ {name}: {msg}")
            continue
        status = "✓" if ok else "✗"
        _print(f"  {status} {name}: {msg}")
        if not ok and not name.startswith("Tier"):
            all_ok = False
        if ok and name.startswith("Tier"):
            available_tiers.append(name)

    _print(f"  → Available tiers: {', '.join(available_tiers) if available_tiers else 'NONE'}")

    if not quiet:
        check_vps_health()

    if not available_tiers:
        print(
            "\n  ⚠️  No tiers available. Install Ollama for Tier C ($0): "
            "curl -fsSL https://ollama.com/install.sh | sh"
        )
        sys.exit(1)

    if not all_ok:
        _print(
            "\n  ⚠️  Some components have issues. The system will run with the available tiers."
        )

    _print("────────────────────────────────")

    # Security hardening
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("db_security", Path(__file__).parent / "db_security.py")
        _db_sec = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_db_sec)
        _db_sec.secure_db_permissions()
        _db_sec.secure_env_permissions()
    except Exception as _e:
        print(f"  ⚠️  Security hardening skipped: {_e}")

    # Hardware profile
    try:
        import importlib.util as _ilu
        _spec2 = _ilu.spec_from_file_location("system_profile", Path(__file__).parent / "system_profile.py")
        _sp = _ilu.module_from_spec(_spec2)
        _spec2.loader.exec_module(_sp)
        _profile = _sp.detect_hardware()
        _ram = _profile["ram"].get("total_mb", "?")
        _cores = _profile["cpu"]["cores"]
        print(f"  Hardware: {_cores} cores, {_ram}MB RAM → recommended Tier C: {_profile['recommended_model']}")
    except Exception as _e:
        print(f"  ⚠️  Hardware detection skipped: {_e}")

    # Verify .env is not tracked by git
    ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
    _tracked = subprocess.run(
        ["git", "ls-files", ".env"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if _tracked.stdout.strip():
        print("  ⚠️  CRITICAL: .env is tracked by git! Run: git rm --cached .env")

    return 0


if __name__ == "__main__":
    sys.exit(main())
