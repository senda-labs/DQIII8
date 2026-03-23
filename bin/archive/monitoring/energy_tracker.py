#!/usr/bin/env python3
"""
DQIII8 — Energy Tracker

Estimates energy consumption per task.
- Tier C (local/Ollama): estimates from CPU TDP * duration
- Tier B/A/S (API): negligible local energy, network-only

Usage:
    from energy_tracker import estimate_energy_wh, record_energy
    wh = estimate_energy_wh(tier="local", duration_ms=5000, cpu_percent=40.0)
"""

import os
import sqlite3
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS / "database" / "jarvis_metrics.db"

# Rough CPU TDP estimates by architecture (watts)
_TDP_ESTIMATES = {
    "x86_64": 65,   # typical server/desktop CPU
    "aarch64": 15,  # ARM server (e.g., Graviton, Ampere)
    "arm64": 8,     # Apple Silicon or embedded ARM
}


def _cpu_tdp_watts() -> float:
    """Estimate CPU TDP in watts based on current platform architecture."""
    import platform
    arch = platform.machine()
    return float(_TDP_ESTIMATES.get(arch, 65))


def estimate_energy_wh(
    tier: str,
    duration_ms: int,
    cpu_percent: float = 100.0,
) -> float:
    """
    Estimate energy consumed in watt-hours.

    For Tier C (local models), estimate based on CPU TDP and utilization.
    For API tiers (B/A/S), return a small fixed network estimate (~0.0001 Wh).
    """
    if tier in ("local", "tier_c", "ollama", "1"):
        tdp = _cpu_tdp_watts()
        utilization = max(0.0, min(cpu_percent, 100.0)) / 100.0
        duration_hours = duration_ms / 1000 / 3600
        return round(tdp * utilization * duration_hours, 8)
    else:
        # API call — negligible local energy, just network overhead
        return 0.0001


def record_energy(
    action_id: int,
    tier: str,
    duration_ms: int,
    cpu_percent: float = 100.0,
) -> float:
    """Compute energy for an action and update agent_actions row."""
    wh = estimate_energy_wh(tier=tier, duration_ms=duration_ms, cpu_percent=cpu_percent)
    if not DB_PATH.exists():
        return wh
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute(
            "UPDATE agent_actions SET energy_wh = ?, cpu_percent = ? WHERE id = ?",
            (wh, cpu_percent, action_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass
    return wh


def get_monthly_energy_wh() -> float:
    """Return total energy consumed (Wh) in the current calendar month."""
    if not DB_PATH.exists():
        return 0.0
    from datetime import datetime
    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        row = conn.execute(
            "SELECT SUM(energy_wh) FROM agent_actions WHERE timestamp >= ?",
            (month_start,),
        ).fetchone()
        conn.close()
        return round(row[0] or 0.0, 6)
    except sqlite3.OperationalError:
        return 0.0


if __name__ == "__main__":
    # Quick self-test
    wh_local = estimate_energy_wh("local", 5000, 80.0)
    wh_api = estimate_energy_wh("tier_a", 5000, 5.0)
    monthly = get_monthly_energy_wh()
    print(f"Local 5s @ 80% CPU: {wh_local:.6f} Wh")
    print(f"API call 5s: {wh_api:.6f} Wh")
    print(f"Monthly total: {monthly:.4f} Wh")
