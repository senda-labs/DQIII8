#!/usr/bin/env python3
"""
DQIII8 — Integration Proposer
Reads APROBADO_PENDIENTE_INTEGRACION items from research_items,
writes a proposal.md, and sends a Telegram notification.

Usage:
    python3 bin/integration_proposer.py
    python3 bin/integration_proposer.py --dry-run
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"
PROPOSALS_DIR = JARVIS_ROOT / "tasks" / "integration_proposals"


def _send_telegram(message: str) -> bool:
    token = os.environ.get("JARVIS_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        urllib.request.urlopen(url, data, timeout=10)
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="DQIII8 integration proposer")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing/sending")
    args = parser.parse_args()

    if not DB.exists():
        print("[integration_proposer] DB not found — skipping")
        sys.exit(0)

    conn = sqlite3.connect(str(DB), timeout=5)
    approved = conn.execute(
        "SELECT id, title, url, summary, score, test_result "
        "FROM research_items WHERE status='APROBADO_PENDIENTE_INTEGRACION'"
    ).fetchall()
    conn.close()

    if not approved:
        print("[integration_proposer] No items pending integration.")
        sys.exit(0)

    print(f"[integration_proposer] {len(approved)} item(s) to propose.")

    PROPOSALS_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")

    for item_id, title, url, summary, score, test_result_json in approved:
        test_info = {}
        try:
            test_info = json.loads(test_result_json or "{}")
        except Exception:
            pass

        proposal_text = (
            f"# Integration Proposal — {title[:70]}\n\n"
            f"Date: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"Research score: {score:.1f}\n"
            f"Shannon: {test_info.get('shannon', '?')}\n"
            f"URL: {url or 'N/A'}\n\n"
            f"## Summary\n{summary or 'N/A'}\n\n"
            f"## Suggested Integration\n"
            f"Review the linked resource and determine if DQIII8 can benefit from:\n"
            f"- Adopting the technique/pattern described\n"
            f"- Adding a new skill or agent capability\n"
            f"- Updating an existing component\n\n"
            f"## Commands\n"
            f"Use `/integrar {item_id}` to mark as integrated\n"
            f"Use `/rechazar {item_id}` to reject\n"
        )

        if args.dry_run:
            print(f"\n--- Proposal for item {item_id} ---")
            print(proposal_text[:400])
        else:
            proposal_file = PROPOSALS_DIR / f"{ts}_proposal_{item_id}.md"
            proposal_file.write_text(proposal_text, encoding="utf-8")

            # Telegram notification
            tg_msg = (
                f"[DQIII8] Nueva propuesta de integracion\n"
                f"Score: {score:.1f} | Shannon: {test_info.get('shannon', '?')}\n"
                f"{title[:80]}\n"
                f"Ver: tasks/integration_proposals/{proposal_file.name}\n\n"
                f"/integrar_{item_id} — aprobar\n"
                f"/rechazar_{item_id} — rechazar"
            )
            sent = _send_telegram(tg_msg)
            print(
                f"[integration_proposer] Proposal written: {proposal_file.name} | Telegram: {'OK' if sent else 'SKIP'}"
            )

    if not args.dry_run:
        print(f"[integration_proposer] Done — {len(approved)} proposals created.")


if __name__ == "__main__":
    main()
