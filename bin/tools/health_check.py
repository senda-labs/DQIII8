#!/usr/bin/env python3
"""DQIII8 daily health check — score 0-100, alert via notify if < 70.

Checks (weights):
  DB integrity ok ............ 30
  unresolved errors (7d) ..... 25  (0 → full; >=20 → 0; linear between)
  telemetry alive (7d) ....... 25  (share of amplification rows with confidence > 0)
  disk free >= 15% ............ 10
  history db readonly ........ 10
Writes JSON to database/audit_reports/health_<date>.json.
Exit code 0 always (cron-safe); alerting is the signal.
"""
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "database" / "dqiii8.db"
OUT = ROOT / "database" / "audit_reports"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    score, detail = 0, {}
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    detail["db_integrity"] = ok
    score += 30 if ok else 0

    n_err = conn.execute(
        "SELECT COUNT(*) FROM error_log WHERE resolved=0 AND timestamp > datetime('now','-7 days')"
    ).fetchone()[0]
    detail["unresolved_errors_7d"] = n_err
    score += max(0, round(25 * (1 - min(n_err, 20) / 20)))

    # Telemetry alive = rows carry the full column set written by the fixed
    # _log_amplification INSERT. NOT confidence>0: confidence is legitimately
    # 0.0 when a prompt has no intent keyword, so that proxy penalized normal
    # traffic (live score 79 vs reported 95 on 2026-06-10 — metric bug).
    total, alive = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN intent_pattern IS NOT NULL "
        "AND routing_method IS NOT NULL AND tier_selected IS NOT NULL "
        "THEN 1 ELSE 0 END) "
        "FROM amplification_log WHERE created_at > datetime('now','-7 days')"
    ).fetchone()
    rate = (alive or 0) / total if total else 1.0
    detail["telemetry_alive_rate_7d"] = round(rate, 2)
    detail["amplification_rows_7d"] = total
    score += round(25 * rate)

    du = shutil.disk_usage(ROOT)
    free = du.free / du.total
    detail["disk_free_pct"] = round(free * 100, 1)
    score += 10 if free >= 0.15 else 0

    # Informational (not scored): Ollama embedding backend reachability
    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            detail["ollama_running"] = r.status == 200
    except Exception:
        detail["ollama_running"] = False

    hist = ROOT / "database" / "dqiii8_history.db"
    ro = hist.exists() and not (hist.stat().st_mode & 0o222)
    detail["history_db_readonly"] = ro
    score += 10 if ro else 0

    report = {"date": datetime.now().isoformat(), "score": score, "detail": detail}
    out = OUT / f"health_{datetime.now():%Y-%m-%d}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    if score < 70:
        try:
            sys.path.insert(0, str(ROOT / "bin" / "core"))
            from notify import notify
            notify(f"DQIII8 health {score}/100 < 70 — {out.name}")
        except Exception as exc:
            print(f"alert dispatch failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
