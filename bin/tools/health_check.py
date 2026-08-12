#!/usr/bin/env python3
"""DQIII8 daily health check — score 0-100, alert via notify if < 70.

Checks (weights):
  DB integrity ok ............ 30
  unresolved errors (7d) ..... 25  (0 → full; >=20 → 0; linear between)
  telemetry alive (7d) ....... 25  (share of amplification rows with confidence > 0)
  disk free >= 15% ............ 10
  history db owner-only ...... 10
Penalty:
  hook telemetry stale ...... floor score at 55 (no agent_actions row in 48h
                                    while amplification_log shows 7d activity)
Separately, unscored: alerts if bin/monitoring/health_watchdog.py's own
heartbeat (var/watchdog_heartbeat) is missing or >24h stale — the two rails'
mutual dead-man's-switch.
Writes JSON to database/audit_reports/health_<date>.json.
Exit code 0 always (cron-safe); alerting is the signal.
"""

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
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

    # Hook telemetry freshness. agent_actions is written only by the project
    # PreToolUse/PostToolUse hooks; it went silent 2026-07-05..08-11 because
    # sessions launched with cwd inside sub-project git repos never loaded
    # /root/dqiii8/.claude/settings.json. Penalty (not a weighted check) so the
    # existing 100-point split is unchanged. Only fires when the system is
    # demonstrably active (amplification rows in 7d) yet agent_actions is stale.
    # Degrades to "unknown" rather than raising: agent_actions is absent on a
    # partial install and a concurrent writer can still surface a lock error, and
    # this runs from cron where an exception means no report and no alert at all.
    try:
        last_action = conn.execute("SELECT MAX(timestamp) FROM agent_actions").fetchone()[0]
        recent_actions = conn.execute(
            "SELECT COUNT(*) FROM agent_actions WHERE timestamp > datetime('now','-2 days')"
        ).fetchone()[0]
        detail["agent_actions_last"] = last_action
        stale = recent_actions == 0
        detail["hook_telemetry_stale"] = bool(stale and total)
        if stale and total:
            # Absolute floor, not a subtraction: a plain -25 lands a clean
            # 100 baseline on 75, which never crosses the <70 alert line —
            # the exact scenario (total hook-telemetry outage) this penalty
            # exists to catch. min(score, 55) always crosses it.
            detail["score_before_stale_floor"] = score
            score = min(score, 55)
    except sqlite3.Error as exc:
        detail["agent_actions_last"] = None
        detail["hook_telemetry_stale"] = None
        detail["hook_telemetry_error"] = str(exc)

    # dqiii8_history.db is the LIVE session_memory store (working_memory.py
    # writes to it); the 2026-06-10 rename-to-readonly-archive ADR was reverted
    # in openrouter_wrapper._enforce_sensitive_permissions. The old
    # "not writable" test could therefore never pass and silently capped the
    # score at 90. Check what is actually required: owner-only permissions.
    hist = ROOT / "database" / "dqiii8_history.db"
    secure = hist.exists() and (hist.stat().st_mode & 0o777) in (0o600, 0o640)
    detail["history_db_owner_only"] = secure
    score += 10 if secure else 0

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

    # Dead-man's-switch, unscored so it can't be masked by the 100-point
    # system (that trap is exactly what the stale-floor fix above closes for
    # the other check). Compared aware-to-aware: health_watchdog.py writes
    # the heartbeat via datetime.now(timezone.utc), not this module's naive
    # datetime.now() used elsewhere above — mixing them raises TypeError.
    try:
        heartbeat_path = ROOT / "var" / "watchdog_heartbeat"
        if not heartbeat_path.exists():
            sys.path.insert(0, str(ROOT / "bin" / "core"))
            from notify import notify

            notify("DQIII8 watchdog heartbeat missing (never written)")
        else:
            raw = heartbeat_path.read_text().strip()
            try:
                hb_time = datetime.fromisoformat(raw)
                if hb_time.tzinfo is None:
                    hb_time = hb_time.replace(tzinfo=timezone.utc)
            except ValueError:
                hb_time = datetime.fromtimestamp(heartbeat_path.stat().st_mtime, tz=timezone.utc)
            age_h = (datetime.now(timezone.utc) - hb_time).total_seconds() / 3600
            if age_h > 24:
                sys.path.insert(0, str(ROOT / "bin" / "core"))
                from notify import notify

                notify(f"DQIII8 watchdog heartbeat stale since {hb_time.isoformat()}")
    except Exception as exc:
        print(f"heartbeat check failed: {exc!r}", file=sys.stderr)


if __name__ == "__main__":
    # The module contract above is "exit code 0 always (cron-safe)": a crash here
    # is itself a health signal and must not look like a silent success, but it
    # also must not make cron treat the job as broken and stop reporting.
    try:
        main()
    except Exception as exc:
        print(f"health_check failed: {exc!r}", file=sys.stderr)
        try:
            sys.path.insert(0, str(ROOT / "bin" / "core"))
            from notify import notify

            notify(f"DQIII8 health_check crashed: {exc!r}")
        except Exception as exc2:
            print(f"alert dispatch failed: {exc2}", file=sys.stderr)
