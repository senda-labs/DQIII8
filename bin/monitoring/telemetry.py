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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, DB_PATH

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
TELEMETRY_ENABLED = os.environ.get("DQIII8_TELEMETRY", "false").lower() == "true"
TELEMETRY_ENDPOINT = os.environ.get("DQIII8_TELEMETRY_URL", "")
VERSION = "0.1.0"


def get_anonymous_id() -> str:
    """Generate a stable anonymous ID from machine characteristics.
    This is NOT reversible to identify the user."""
    raw = f"{platform.node()}-{platform.machine()}-{os.getuid()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def collect_model_performance() -> dict:
    """Collect anonymous model performance metrics.
    These help optimize routing decisions for all users.
    No prompts or outputs are included."""
    if not DB_PATH.exists():
        return {}

    with get_db(timeout=5) as conn:
        week_ago = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Performance by tier (no content — latency, cost, success only)
        rows = conn.execute(
            """SELECT
                   tier,
                   COUNT(*) as total_calls,
                   ROUND(AVG(success) * 100, 1) as success_rate,
                   ROUND(AVG(duration_ms), 0) as avg_latency_ms,
                   ROUND(AVG(tokens_input), 0) as avg_tokens_in,
                   ROUND(AVG(tokens_output), 0) as avg_tokens_out,
                   ROUND(SUM(estimated_cost_usd), 4) as total_cost,
                   ROUND(AVG(estimated_cost_usd), 6) as avg_cost_per_call
               FROM agent_actions
               WHERE timestamp > ?
               GROUP BY tier""",
            (week_ago,),
        ).fetchall()

        model_perf = {
            (r[0] or "unknown"): {
                "calls": r[1],
                "success_rate": r[2],
                "avg_latency_ms": r[3],
                "avg_tokens_in": r[4],
                "avg_tokens_out": r[5],
                "total_cost_usd": r[6],
                "avg_cost_per_call": r[7],
            }
            for r in rows
        }

        # Escalation patterns (error_log has no tier column — group by agent_name)
        esc_rows = conn.execute(
            """SELECT agent_name, COUNT(*) FROM error_log
               WHERE keywords LIKE '%ESCALATION%' AND timestamp > ?
               GROUP BY agent_name""",
            (week_ago,),
        ).fetchall()
        escalation_data = {(r[0] or "unknown"): r[1] for r in esc_rows}

        # Domain-tier routing performance
        domain_rows = conn.execute(
            """SELECT domain, tier, COUNT(*), ROUND(AVG(success) * 100, 1)
               FROM agent_actions
               WHERE timestamp > ? AND domain IS NOT NULL
               GROUP BY domain, tier""",
            (week_ago,),
        ).fetchall()
        domain_routing: dict = {}
        for domain, tier, calls, success in domain_rows:
            domain_routing.setdefault(domain, {})[tier or "unknown"] = {
                "calls": calls,
                "success_rate": success,
            }

        # Knowledge enrichment impact
        enrichment = conn.execute(
            """SELECT
                   ROUND(AVG(CASE WHEN domain_enriched = 1 THEN success ELSE NULL END) * 100, 1),
                   ROUND(AVG(CASE WHEN domain_enriched = 0 THEN success ELSE NULL END) * 100, 1),
                   SUM(CASE WHEN domain_enriched = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN domain_enriched = 0 THEN 1 ELSE 0 END)
               FROM agent_actions WHERE timestamp > ?""",
            (week_ago,),
        ).fetchone()

    return {
        "model_performance": model_perf,
        "escalation_patterns": escalation_data,
        "domain_routing": domain_routing,
        "enrichment_impact": {
            "enriched_success_rate": enrichment[0],
            "plain_success_rate": enrichment[1],
            "enriched_calls": enrichment[2],
            "plain_calls": enrichment[3],
        }
        if enrichment
        else {},
    }


def collect_anonymous_metrics() -> dict:
    """Collect metrics that are safe to share."""
    if not DB_PATH.exists():
        return {}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    with get_db(timeout=5) as conn:
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

    total_disk, _, free_disk = shutil.disk_usage("/")

    metrics = {
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

    # Add model performance metrics
    perf = collect_model_performance()
    metrics["model_performance"] = perf.get("model_performance", {})
    metrics["escalation_patterns"] = perf.get("escalation_patterns", {})
    metrics["domain_routing"] = perf.get("domain_routing", {})
    metrics["enrichment_impact"] = perf.get("enrichment_impact", {})

    return metrics


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
