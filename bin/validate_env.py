#!/usr/bin/env python3
"""Valida el entorno de DQIII8 al arrancar. Reporta qué tiers están disponibles."""

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
            return True, "qwen2.5-coder:7b detectado"
        elif result.returncode == 0:
            return (
                False,
                "Ollama activo pero qwen2.5-coder no instalado. Ejecuta: ollama pull qwen2.5-coder:7b",
            )
        return False, "Ollama no responde"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "Ollama no instalado o no accesible"


def check_tier_b():
    """Tier B: Groq o OpenRouter free."""
    groq = os.environ.get("GROQ_API_KEY", "")
    openrouter = os.environ.get("OPENROUTER_API_KEY", "")
    if groq:
        return True, "GROQ_API_KEY configurada"
    elif openrouter:
        return True, "OPENROUTER_API_KEY configurada (fallback)"
    return False, "GROQ_API_KEY y OPENROUTER_API_KEY no definidas. Tier B no disponible."


def check_tier_a():
    """Tier A: Claude API."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return True, "ANTHROPIC_API_KEY configurada"
    return False, "ANTHROPIC_API_KEY no definida. Tier A no disponible."


def check_db():
    """Verifica que la DB existe y es accesible."""
    root = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
    db_path = root / "database" / "jarvis_metrics.db"
    if not db_path.exists():
        return False, f"DB no encontrada en {db_path}"
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("SELECT 1")
        conn.close()
        return True, "jarvis_metrics.db accesible"
    except Exception as e:
        return False, f"DB error: {e}"


def check_telegram():
    """Verifica Telegram bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return True, "Telegram configurado"
    return (
        False,
        "TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no definidos. Notificaciones deshabilitadas.",
    )


def check_vps_health():
    """Chequeo básico de recursos del VPS."""
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
    root = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
    db_path = root / "database" / "jarvis_metrics.db"
    if db_path.exists():
        db_size_mb = db_path.stat().st_size / (1024**2)
        if db_size_mb > 100:
            print(f"  ⚠️  DB size: {db_size_mb:.0f}MB (considerar VACUUM)")
        else:
            print(f"  ✓ DB size: {db_size_mb:.1f}MB")


def main():
    checks = [
        ("Tier C (local, $0)", check_tier_c),
        ("Tier B (cloud free)", check_tier_b),
        ("Tier A (cloud paid)", check_tier_a),
        ("Database", check_db),
        ("Telegram", check_telegram),
    ]

    all_ok = True
    available_tiers = []

    print("─── DQIII8 Environment Check ───")
    for name, check_fn in checks:
        ok, msg = check_fn()
        status = "✓" if ok else "✗"
        print(f"  {status} {name}: {msg}")
        if not ok and not name.startswith("Tier"):
            all_ok = False
        if ok and name.startswith("Tier"):
            available_tiers.append(name)

    print(f"  → Tiers disponibles: {', '.join(available_tiers) if available_tiers else 'NINGUNO'}")

    check_vps_health()

    if not available_tiers:
        print(
            "\n  ⚠️  Sin tiers disponibles. Instala Ollama para Tier C ($0): "
            "curl -fsSL https://ollama.com/install.sh | sh"
        )
        sys.exit(1)

    if not all_ok:
        print(
            "\n  ⚠️  Hay componentes con problemas. El sistema funcionará con los tiers disponibles."
        )

    print("────────────────────────────────")
    return 0


if __name__ == "__main__":
    sys.exit(main())
