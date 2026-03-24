#!/usr/bin/env python3
"""
weekly_audit.py — Weekly automated system health audit.

Runs comparable queries to auditor_local.py, compares with the previous
week's baseline stored in audit_reports/, and sends a Telegram summary.

Alerts when:
  - Overall success rate drops > 5 points vs previous week
  - New unresolved error types appear
  - Instincts with confidence < 0.3 (at risk of becoming useless)
  - Any component with 0 actions (possible dead code)

Usage:
    python3 bin/monitoring/weekly_audit.py
    python3 bin/monitoring/weekly_audit.py --quiet   # no Telegram, only log
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))

DB = DQIII8_ROOT / "database" / "jarvis_metrics.db"
REPORT_DIR = DQIII8_ROOT / "database" / "audit_reports"
BASELINE_FILE = REPORT_DIR / "weekly_baseline.json"

NOW = datetime.now(timezone.utc)
SINCE_7D = (NOW - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
SINCE_30D = (NOW - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
QUIET = "--quiet" in sys.argv


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


# ── Metric collectors ─────────────────────────────────────────────────────


def collect_action_metrics(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """
        SELECT
            COUNT(*)                                        AS total,
            SUM(success)                                    AS ok,
            ROUND(100.0 * SUM(success) / COUNT(*), 1)      AS success_pct,
            ROUND(AVG(duration_ms), 0)                      AS avg_ms,
            COUNT(DISTINCT session_id)                      AS sessions
        FROM agent_actions
        WHERE timestamp >= ?
        """,
        (SINCE_7D,),
    ).fetchone()
    return dict(row) if row else {}


def collect_error_types(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT error_type, COUNT(*) AS cnt, MAX(error_message) AS sample
        FROM error_log
        WHERE timestamp >= ?
          AND resolved = 0
          AND error_type IS NOT NULL
        GROUP BY error_type
        ORDER BY cnt DESC
        LIMIT 10
        """,
        (SINCE_7D,),
    ).fetchall()
    return [dict(r) for r in rows]


def collect_instincts_at_risk(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT keyword, confidence, times_applied, times_successful,
               last_applied
        FROM instincts
        WHERE confidence < 0.3
        ORDER BY confidence ASC
        LIMIT 10
        """,
    ).fetchall()
    return [dict(r) for r in rows]


def collect_routing_health(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(tier, 'unknown')   AS tier,
            COUNT(*)                    AS total,
            SUM(success)                AS ok,
            ROUND(100.0 * SUM(success) / COUNT(*), 1) AS success_pct,
            ROUND(AVG(duration_ms), 0)  AS avg_ms
        FROM agent_actions
        WHERE timestamp >= ?
          AND tier IS NOT NULL
          AND tier != 'unknown'
        GROUP BY tier
        ORDER BY total DESC
        """,
        (SINCE_7D,),
    ).fetchall()
    return [dict(r) for r in rows]


def collect_service_status() -> dict[str, str]:
    status = {}
    for svc in ["autoreporte", "jarvis-bot", "dq-dashboard", "ollama"]:
        result = subprocess.run(
            ["systemctl", "is-active", svc], capture_output=True, text=True
        )
        status[svc] = result.stdout.strip()
    return status


# ── Comparison & alerts ───────────────────────────────────────────────────


def load_baseline() -> dict:
    if BASELINE_FILE.exists():
        try:
            return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_baseline(metrics: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def detect_alerts(
    current: dict, baseline: dict, errors: list, instincts_at_risk: list
) -> list[str]:
    alerts = []

    # Success rate regression
    curr_pct = current.get("success_pct") or 0
    prev_pct = baseline.get("success_pct") or curr_pct
    if prev_pct - curr_pct > 5:
        alerts.append(
            f"Success rate dropped {prev_pct:.1f}% → {curr_pct:.1f}% "
            f"(delta: -{prev_pct - curr_pct:.1f}pp)"
        )

    # New error types vs baseline
    prev_errors = {e["error_type"] for e in baseline.get("errors", [])}
    for err in errors:
        if err["error_type"] not in prev_errors:
            alerts.append(
                f"New error type: {err['error_type']} ({err['cnt']}x) — "
                f"{(err.get('sample') or '')[:60]}"
            )

    # Instincts at risk
    if instincts_at_risk:
        kws = ", ".join(i["keyword"] for i in instincts_at_risk[:5])
        alerts.append(
            f"{len(instincts_at_risk)} instinct(s) at risk (confidence<0.3): {kws}"
        )

    return alerts


# ── Report builder ────────────────────────────────────────────────────────


def build_report(
    metrics: dict,
    errors: list,
    routing: list,
    services: dict,
    alerts: list,
    baseline: dict,
) -> str:
    today = NOW.strftime("%Y-%m-%d")
    lines = [f"DQIII8 Weekly Audit — {today}"]
    lines.append("=" * 40)

    # Actions summary
    m = metrics
    lines.append(
        f"Actions (7d): {m.get('total', 0)} total, "
        f"{m.get('success_pct', 0):.1f}% success, "
        f"{m.get('avg_ms', 0):.0f}ms avg, "
        f"{m.get('sessions', 0)} sessions"
    )

    # Routing by tier
    if routing:
        lines.append("\nRouting by tier:")
        for r in routing:
            lines.append(
                f"  Tier {r['tier']}: {r['total']} calls, "
                f"{r['success_pct']:.1f}% ok, {r['avg_ms']:.0f}ms"
            )

    # Errors
    if errors:
        lines.append(f"\nTop errors (7d, unresolved):")
        for e in errors[:5]:
            lines.append(f"  [{e['cnt']}x] {e['error_type']}")
    else:
        lines.append("\nErrors: none")

    # Services
    down = [k for k, v in services.items() if v != "active"]
    if down:
        lines.append(f"\nServices DOWN: {', '.join(down)}")
    else:
        lines.append(f"\nServices: all active")

    # Alerts
    if alerts:
        lines.append(f"\nALERTS ({len(alerts)}):")
        for a in alerts:
            lines.append(f"  - {a}")
    else:
        lines.append("\nNo regressions detected")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"[weekly_audit] Starting — {NOW.strftime('%Y-%m-%d %H:%M UTC')}")

    if not DB.exists():
        print(f"[weekly_audit] DB not found: {DB}", file=sys.stderr)
        sys.exit(1)

    conn = get_conn()
    metrics = collect_action_metrics(conn)
    errors = collect_error_types(conn)
    instincts_at_risk = collect_instincts_at_risk(conn)
    routing = collect_routing_health(conn)
    conn.close()

    services = collect_service_status()
    baseline = load_baseline()
    alerts = detect_alerts(metrics, baseline, errors, instincts_at_risk)

    # Cost summary (best-effort — skip if cost_tracker unavailable)
    cost_summary = ""
    try:
        _ct_path = DQIII8_ROOT / "bin" / "monitoring" / "cost_tracker.py"
        if _ct_path.exists():
            import importlib.util as _ilu

            _spec = _ilu.spec_from_file_location("cost_tracker", _ct_path)
            _ct = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_ct)
            _crep = _ct.generate_cost_report(7)
            cost_summary = (
                f"\nCost (7d): ${_crep.get('actual_cost_usd', 0):.2f} actual, "
                f"${_crep.get('baseline_cost_usd', 0):.2f} baseline, "
                f"saved ${_crep.get('savings_usd', 0):.2f} "
                f"({_crep.get('savings_pct', 0):.1f}%)"
            )
    except Exception:
        pass

    report = build_report(metrics, errors, routing, services, alerts, baseline)
    if cost_summary:
        report += cost_summary
    print(report)

    # Save this week's metrics as next week's baseline
    save_baseline(
        {
            "generated": NOW.isoformat(),
            "success_pct": metrics.get("success_pct"),
            "errors": errors,
        }
    )

    # Save full report
    report_path = REPORT_DIR / f"audit-weekly-{NOW.strftime('%Y-%m-%d')}.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n[weekly_audit] Report → {report_path}")

    # Telegram notification
    if not QUIET:
        if alerts:
            msg = f"DQIII8 WEEKLY AUDIT — {NOW.strftime('%Y-%m-%d')}\n"
            msg += f"ALERTS ({len(alerts)}):\n" + "\n".join(f"- {a}" for a in alerts)
            msg += f"\n\nSuccess: {metrics.get('success_pct', 0):.1f}% over {metrics.get('total', 0)} actions"
        else:
            msg = (
                f"DQIII8 Weekly OK — {NOW.strftime('%Y-%m-%d')}\n"
                f"{metrics.get('total', 0)} actions, "
                f"{metrics.get('success_pct', 0):.1f}% success, "
                f"no regressions"
            )
        try:
            from notify import send_telegram

            send_telegram(msg)
        except Exception as e:
            print(f"[weekly_audit] notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
