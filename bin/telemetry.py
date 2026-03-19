#!/usr/bin/env python3
"""
DQIII8 Anonymous Telemetry — 100% opt-in.

This module sends anonymous usage metrics to help improve DQIII8.
It is DISABLED by default. Enable with: DQIII8_TELEMETRY=true in .env

What we collect (all anonymous, no PII):
- Tier usage distribution (e.g., 70% C, 20% B, 10% A)
- Success rate per tier
- Domain classification distribution
- Error type counts (not messages)
- Session count and average duration
- Health score
- OS version, Python version, RAM, available disk
- DQIII8 version

What we NEVER collect:
- Prompts, outputs, or any content
- API keys or credentials
- File names, paths, or directory structure
- IP address (we use a privacy-respecting endpoint)
- Any personally identifiable information
"""
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS / "database" / "jarvis_metrics.db"
TELEMETRY_ENABLED = os.environ.get("DQIII8_TELEMETRY", "false").lower() == "true"
TELEMETRY_ENDPOINT = os.environ.get("DQIII8_TELEMETRY_URL", "")
VERSION = "0.1.0"


def get_anonymous_id() -> str:
    """Generate a stable anonymous ID from machine characteristics.
    This is NOT reversible to identify the user."""
    raw = f"{platform.node()}-{platform.machine()}-{os.getuid()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def collect_anonymous_metrics() -> dict:
    """Collect metrics that are safe to share."""
    if not DB_PATH.exists():
        return {}

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # Tier distribution
    rows = conn.execute(
        "SELECT tier, COUNT(*) FROM agent_actions WHERE timestamp > ? GROUP BY tier",
        (week_ago,),
    ).fetchall()
    total = sum(r[1] for r in rows) or 1
    tier_dist = {(r[0] or "unknown"): round(r[1] / total, 3) for r in rows}

    # Success rate per tier
    rows = conn.execute(
        "SELECT tier, ROUND(AVG(success) * 100, 1) FROM agent_actions WHERE timestamp > ? GROUP BY tier",
        (week_ago,),
    ).fetchall()
    success_rates = {(r[0] or "unknown"): r[1] for r in rows}

    # Domain distribution
    rows = conn.execute(
        "SELECT domain, COUNT(*) FROM agent_actions WHERE timestamp > ? AND domain IS NOT NULL GROUP BY domain",
        (week_ago,),
    ).fetchall()
    domain_dist = {r[0]: r[1] for r in rows}

    # Error types (counts only, no messages)
    rows = conn.execute(
        "SELECT error_type, COUNT(*) FROM error_log WHERE timestamp > ? GROUP BY error_type",
        (week_ago,),
    ).fetchall()
    error_types = {(r[0] or "unknown"): r[1] for r in rows}

    # Session stats
    session_stats = conn.execute(
        """SELECT COUNT(*), AVG(
            CASE WHEN end_time IS NOT NULL
            THEN (julianday(end_time) - julianday(start_time)) * 86400
            END
           ) FROM sessions WHERE start_time > ?""",
        (week_ago,),
    ).fetchone()

    # Health score
    health = conn.execute(
        "SELECT overall_score FROM audit_reports ORDER BY period_end DESC LIMIT 1"
    ).fetchone()

    conn.close()

    total_disk, _, free_disk = shutil.disk_usage("/")

    return {
        "anonymous_id": get_anonymous_id(),
        "version": VERSION,
        "timestamp": now.isoformat() + "Z",
        "system": {
            "os": platform.system(),
            "os_version": platform.release(),
            "python": platform.python_version(),
            "arch": platform.machine(),
            "ram_mb": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024**2),
            "disk_free_gb": round(free_disk / (1024**3), 1),
        },
        "usage": {
            "tier_distribution": tier_dist,
            "success_rates": success_rates,
            "domain_distribution": domain_dist,
            "error_type_counts": error_types,
            "sessions_7d": session_stats[0] if session_stats else 0,
            "avg_session_seconds": (
                round(session_stats[1], 0) if session_stats and session_stats[1] else None
            ),
            "health_score": health[0] if health else None,
        },
    }


def send_telemetry():
    """Send anonymous metrics if opt-in is enabled."""
    if not TELEMETRY_ENABLED:
        return {
            "status": "disabled",
            "message": "Telemetry is opt-in. Set DQIII8_TELEMETRY=true in .env to enable.",
        }

    metrics = collect_anonymous_metrics()

    if not TELEMETRY_ENDPOINT:
        # Save locally until endpoint is configured
        outdir = JARVIS / "database" / "telemetry"
        outdir.mkdir(exist_ok=True)
        outfile = outdir / f"metrics-{datetime.utcnow().strftime('%Y%m%d')}.json"
        outfile.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        return {"status": "saved_locally", "file": str(outfile)}

    import requests

    try:
        resp = requests.post(
            TELEMETRY_ENDPOINT,
            json=metrics,
            timeout=10,
            headers={"User-Agent": f"DQIII8/{VERSION}"},
        )
        return {"status": "sent", "code": resp.status_code}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


if __name__ == "__main__":
    if "--collect" in sys.argv:
        metrics = collect_anonymous_metrics()
        print(json.dumps(metrics, indent=2))
    elif "--send" in sys.argv:
        result = send_telemetry()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 telemetry.py --collect | --send")
        print(f"Telemetry is: {'ENABLED' if TELEMETRY_ENABLED else 'DISABLED'}")
        print("Enable with: DQIII8_TELEMETRY=true in .env")
