#!/usr/bin/env python3
"""Triage the error_log backlog of expected free-tier fallback cascades.

~92% of unresolved error_log rows (openrouter_wrapperError/ESCALATION/nimError/
openrouterError/githubError/groqError/pollinationsError) are the FREE-tier
fallback chain (C→B→B+→B++, see CLAUDE.md Routing Tiers) doing exactly what
it's designed to do when one free provider is briefly unavailable — not
incidents. Nothing ever marks them resolved, and purge_transient_errors.py
only deletes rows with severity='transient' AND resolved=1, so they never
even become eligible for purge; they just accumulate forever.

anthropicError is intentionally EXCLUDED from the whitelist even though it
matches the same message shape — Anthropic is a paid tier (Tier A/S), not a
free-tier fallback rung, so an anthropicError is more likely a real billing/
OAuth incident and auto-resolving it could mask one.

Sets BOTH resolved=1 AND severity='transient' on matched rows (not resolved
alone) — that's what purge_transient_errors.py's WHERE clause requires to
actually reclaim them later; setting only resolved=1 would leave
'operational'-severity rows permanently ineligible for purge.

Correlation (Opus red-team review, 2026-08-13, P1-2): a whitelist match alone
can't distinguish "rung 2 failed, rung 3 answered" from "the whole free tier
is down" — both write the identical message shape, and a total-chain failure
(openrouter_wrapper.py's `sys.exit(1)` path) writes nothing to error_log at
all. So a genuine multi-day outage of the whole free tier would sail through
this script unresolved-then-purged, invisible to health_check.py. Rows that
carry an action_id are only auto-resolved if agent_actions shows a *successful*
row in the same session within CORRELATION_WINDOW_MIN of the error — i.e. the
cascade the error belongs to actually recovered. Rows with no action_id can't
be correlated (mostly older backlog) and fall back to whitelist-only, same as
before. As a second, cheaper safety net independent of correlation: the daily
matched count is compared against a rolling history file, and an anomalous
spike still alerts even for the uncorrelatable rows.

Correlation tightened (Opus red-team review of the above, 2026-08-13, round 2
P1-1): session_id alone was too coarse — `session_id='cli'` is a shared bucket
across unrelated invocations (1000+ agent_actions rows), and a long CLI
session logs successful Reads/Edits constantly regardless of whether the
*specific failing agent* recovered, so "any successful action in this
session" matched ~99% of candidates and would have papered over a real
outage. The successful sibling must now also match error_log.agent_name (the
actual failing component), and `session_id='cli'` is excluded from the
session-window fallback entirely — a shared-bucket session can never supply
correlation evidence, so its rows are always held for review.

Held-rows disposition (Opus red-team review, 2026-08-13, round 3 P1-2): the
cli-bucket exclusion above is correct but a held row is never re-evaluated —
it's still resolved=0 next run, so it reappears in `held_ids` every day
forever. Two consequences, both fixed here: (1) `_check_spike` compared a
monotonically growing cumulative held count against its own rolling median,
so the alert threshold asymptotically became unreachable (quantified live:
~59/day held, spike threshold needs an ~885-row single-day burst after just
30 days of accumulation) — fixed by diffing against the previous run's held
id set (`HELD_STATE_FILE`) so the spike check sees only *newly*-held rows
per run, a real daily rate. (2) held rows that still have no correlation
evidence after HELD_REVIEW_DAYS are auto-resolved with a distinct
resolution note (not `severity='transient'`, so purge_transient_errors.py
never deletes them — the audit trail survives) instead of accumulating in
`error_log` without bound.

Usage:
    python3 bin/tools/triage_error_log.py --dry-run   # show counts, no writes
    python3 bin/tools/triage_error_log.py --apply      # perform the UPDATE
Back up the DB first (bin/tools/db_backup.sh) — this is a bulk UPDATE.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "database" / "dqiii8.db"
HISTORY_FILE = ROOT / "var" / "triage_history.json"
# Previous run's held-id set, for the spike check's day-over-day diff (round 3
# P1-2) — NOT a history/audit file, just last-run state, so it's a single
# snapshot, not append-only.
HELD_STATE_FILE = ROOT / "var" / "triage_held_prev.json"
CORRELATION_WINDOW_MIN = 10
HISTORY_KEEP = 14
SPIKE_MULTIPLIER = 3
# Threshold is against newly-held rows this run (round 3 P1-2 fix), not total
# held backlog — a real per-day rate, so this stays meaningful over time.
SPIKE_MIN_HELD = 10
# Held rows with no correlation evidence after this many days are auto-resolved
# with RESOLUTION_NOTE_AGED instead of accumulating in error_log without bound
# (round 3 P1-2). Short enough that health_check's 7-day unresolved-error
# window isn't permanently saturated by a bucket that can structurally never
# correlate; long enough to leave a real multi-day outage visible to a human
# or the spike check before it's swept.
HELD_REVIEW_DAYS = 3

WHITELIST_ERROR_TYPES = (
    "openrouter_wrapperError",
    "ESCALATION",
    "nimError",
    "openrouterError",
    "githubError",
    "groqError",
    "pollinationsError",
)

MESSAGE_PATTERNS = ("%failed — no response or HTTP error%", "%Escalated from%")

RESOLUTION_NOTE = "auto: expected free-tier fallback cascade"
RESOLUTION_NOTE_AGED = (
    f"auto: expected free-tier fallback cascade (uncorrelated — no successful "
    f"sibling found within {HELD_REVIEW_DAYS}d of held review, aged out)"
)


def _match_where():
    type_placeholders = ",".join("?" for _ in WHITELIST_ERROR_TYPES)
    msg_clause = " OR ".join("error_message LIKE ?" for _ in MESSAGE_PATTERNS)
    where = f"resolved=0 AND error_type IN ({type_placeholders}) AND ({msg_clause})"
    params = list(WHITELIST_ERROR_TYPES) + list(MESSAGE_PATTERNS)
    return where, params


def _correlated_ids(conn, candidates):
    """Split whitelist-matched rows into (resolvable_ids, held).

    held is a list of (id, timestamp) pairs, not bare ids — main() needs the
    timestamp to decide which held rows have aged past HELD_REVIEW_DAYS.

    A row with no action_id can't be correlated — falls back to whitelist-only
    (resolvable). A row with an action_id is only resolvable if agent_actions
    shows a successful row for the SAME agent_name in the same session within
    CORRELATION_WINDOW_MIN — proof the specific cascade it belongs to actually
    recovered, not just that unrelated work happened to succeed nearby.
    `session_id='cli'` is a shared bucket, not a real session — never treated
    as correlation evidence.
    """
    resolvable, held = [], []
    window_days = CORRELATION_WINDOW_MIN / 1440.0
    # Cache per (session_id, agent_name, timestamp) — rows sharing a burst tend
    # to share these, so this avoids re-querying the identical pair repeatedly
    # (round 2 P3-4: was one query per row with no reuse at all).
    cache = {}
    for row_id, action_id, session_id, agent_name, timestamp in candidates:
        if action_id is None:
            resolvable.append(row_id)
            continue
        if session_id == "cli":
            held.append((row_id, timestamp))
            continue
        key = (session_id, agent_name, timestamp)
        if key not in cache:
            cache[key] = conn.execute(
                "SELECT 1 FROM agent_actions WHERE session_id=? AND agent_name=? AND success=1 "
                "AND ABS(julianday(timestamp) - julianday(?)) <= ? LIMIT 1",
                (session_id, agent_name, timestamp, window_days),
            ).fetchone()
        (resolvable.append(row_id) if cache[key] else held.append((row_id, timestamp)))
    return resolvable, held


def _load_prev_held_ids() -> set:
    if not HELD_STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(HELD_STATE_FILE.read_text()))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_held_ids(held_ids) -> None:
    HELD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    HELD_STATE_FILE.write_text(json.dumps(list(held_ids)))


def _check_spike(newly_held: int) -> str | None:
    """Volume safety net independent of correlation — tracks *newly*-held rows
    this run (ids not already held as of the previous run), not the full held
    backlog. Held rows stay resolved=0 until HELD_REVIEW_DAYS, so without this
    diff the same rows would re-inflate the count every day: a real daily rate
    would have needed an ~885-row single-day burst to trip the alert after just
    30 days of accumulation, since the cumulative count only ever grows
    (quantified live, Opus red-team review, 2026-08-13, round 3 P1-2)."""
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            history = []

    alert = None
    if len(history) >= 3 and newly_held >= SPIKE_MIN_HELD:
        sorted_hist = sorted(history)
        median = sorted_hist[len(sorted_hist) // 2]
        if median > 0 and newly_held > median * SPIKE_MULTIPLIER:
            alert = (
                f"triage held {newly_held} newly-uncorrelated rows this run, "
                f">{SPIKE_MULTIPLIER}x the recent median ({median}) — "
                f"possible sustained provider outage, not routine fallback"
            )

    history.append(newly_held)
    history = history[-HISTORY_KEEP:]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history))
    return alert


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    where, params = _match_where()
    conn = sqlite3.connect(DB, timeout=30)

    total_unresolved = conn.execute("SELECT COUNT(*) FROM error_log WHERE resolved=0").fetchone()[0]
    candidates = conn.execute(
        f"SELECT id, action_id, session_id, agent_name, timestamp FROM error_log WHERE {where}", params
    ).fetchall()
    matched = len(candidates)
    resolvable_ids, held = _correlated_ids(conn, candidates)
    held_ids = [row_id for row_id, _ts in held]
    # Rows held past HELD_REVIEW_DAYS with still no correlation evidence are
    # aged out (round 3 P1-2) — resolved with a distinct note, kept out of
    # 'transient' severity so purge_transient_errors.py never deletes them.
    aged_cutoff_days = f"-{HELD_REVIEW_DAYS} days"
    aged_row = conn.execute("SELECT datetime('now', ?)", (aged_cutoff_days,)).fetchone()
    aged_cutoff = aged_row[0]
    aged_ids = [row_id for row_id, ts in held if ts <= aged_cutoff]
    held_fresh_ids = [row_id for row_id, ts in held if ts > aged_cutoff]

    print(f"[triage] unresolved total: {total_unresolved}")
    print(f"[triage] whitelist match: {matched} (correlated-resolvable: {len(resolvable_ids)}, "
          f"held for review — no successful sibling found: {len(held_fresh_ids)}, "
          f"aged out after {HELD_REVIEW_DAYS}d unresolved: {len(aged_ids)})")
    print(f"[triage] remaining for human review: {total_unresolved - len(resolvable_ids) - len(aged_ids)}")

    breakdown = conn.execute(
        f"SELECT error_type, COUNT(*) FROM error_log WHERE {where} GROUP BY error_type ORDER BY 2 DESC",
        params,
    ).fetchall()
    for error_type, n in breakdown:
        print(f"  {error_type}: {n}")

    if args.dry_run:
        # No history/marker write here (Opus red-team review, round 2 P2-1):
        # a --dry-run previously still wrote HISTORY_FILE, which (a) let repeated
        # manual dry-runs flush real daily medians out of the 14-entry rolling
        # window, corrupting the spike baseline, and (b) refreshed the file's
        # mtime, which health_watchdog.check_triage_ran() reads as "the --apply
        # cron is alive" — a dry-run (or a crash before commit) could mask a
        # dead cron for another 48h.
        conn.close()
        return

    if resolvable_ids:
        id_placeholders = ",".join("?" for _ in resolvable_ids)
        conn.execute(
            f"UPDATE error_log SET resolved=1, severity='transient', resolution=? "
            f"WHERE id IN ({id_placeholders})",
            [RESOLUTION_NOTE] + resolvable_ids,
        )
    if aged_ids:
        id_placeholders = ",".join("?" for _ in aged_ids)
        conn.execute(
            f"UPDATE error_log SET resolved=1, resolution=? WHERE id IN ({id_placeholders})",
            [RESOLUTION_NOTE_AGED] + aged_ids,
        )
    if resolvable_ids or aged_ids:
        conn.commit()
    applied = len(resolvable_ids) + len(aged_ids)

    # Spike check + history/marker write happen only after a successful apply
    # (round 2 P2-1) and compare only NEWLY-held rows (round 3 P1-2) — ids not
    # already held as of the previous run — not the cumulative held backlog,
    # which just grows every day since a held row stays resolved=0 until it
    # ages out and would desensitize the check into never firing.
    prev_held = _load_prev_held_ids()
    newly_held = [i for i in held_fresh_ids if i not in prev_held]
    _save_held_ids(held_fresh_ids)
    spike_alert = _check_spike(len(newly_held))
    if spike_alert:
        print(f"[triage] ALERT: {spike_alert}")
        try:
            sys.path.insert(0, str(ROOT / "bin" / "core"))
            from notify import notify

            notify(f"DQIII8 triage_error_log: {spike_alert}")
        except Exception as exc:
            print(f"[triage] alert dispatch failed: {exc}", file=sys.stderr)

    conn.close()
    print(f"[triage] applied: {applied} row(s) updated")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[triage] CRASHED: {exc!r}", file=sys.stderr)
        try:
            sys.path.insert(0, str(ROOT / "bin" / "core"))
            from notify import notify

            notify(f"DQIII8 triage_error_log crashed: {exc!r}")
        except Exception:
            pass
        sys.exit(1)
