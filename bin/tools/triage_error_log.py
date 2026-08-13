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

Usage:
    python3 bin/tools/triage_error_log.py --dry-run   # show counts, no writes
    python3 bin/tools/triage_error_log.py --apply      # perform the UPDATE
Back up the DB first (bin/tools/db_backup.sh) — this is a bulk UPDATE.
"""

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "database" / "dqiii8.db"

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


def _match_where():
    type_placeholders = ",".join("?" for _ in WHITELIST_ERROR_TYPES)
    msg_clause = " OR ".join("error_message LIKE ?" for _ in MESSAGE_PATTERNS)
    where = f"resolved=0 AND error_type IN ({type_placeholders}) AND ({msg_clause})"
    params = list(WHITELIST_ERROR_TYPES) + list(MESSAGE_PATTERNS)
    return where, params


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    where, params = _match_where()
    conn = sqlite3.connect(DB)

    matched = conn.execute(f"SELECT COUNT(*) FROM error_log WHERE {where}", params).fetchone()[0]
    total_unresolved = conn.execute("SELECT COUNT(*) FROM error_log WHERE resolved=0").fetchone()[0]

    print(f"[triage] unresolved total: {total_unresolved}")
    print(f"[triage] whitelist match (will be marked resolved=1, severity=transient): {matched}")
    print(f"[triage] remaining for human review: {total_unresolved - matched}")

    breakdown = conn.execute(
        f"SELECT error_type, COUNT(*) FROM error_log WHERE {where} GROUP BY error_type ORDER BY 2 DESC",
        params,
    ).fetchall()
    for error_type, n in breakdown:
        print(f"  {error_type}: {n}")

    if args.dry_run:
        conn.close()
        return

    conn.execute(
        f"UPDATE error_log SET resolved=1, severity='transient', resolution=? WHERE {where}",
        [RESOLUTION_NOTE] + params,
    )
    conn.commit()
    applied = conn.total_changes
    conn.close()
    print(f"[triage] applied: {applied} row(s) updated")


if __name__ == "__main__":
    main()
