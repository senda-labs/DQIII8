#!/usr/bin/env python3
"""Self-heal check for dq-dashboard.service.

Root cause this exists for: dq-dashboard.service.d/hardening.conf sets
StartLimitBurst=5 / StartLimitIntervalSec=600. Once systemd hits that burst
(any transient failure, e.g. the 2026-09-04 port-bind conflict), it gives up
retrying permanently -- the unit stays in "failed (start-limit-hit)" until a
human runs `systemctl reset-failed` by hand. That incident stayed down
~3h35min for exactly this reason (confirmed via journalctl), not because
detection was slow (the existing OnFailure=dqiii8-alert@%n Telegram alert
fired immediately).

This script only detects and clears that specific stuck state; it does not
touch the original failure cause (see hardening.conf's ExecStartPre for the
port-cleanup fix). Meant to be run frequently (systemd timer, not cron --
this needs to catch the stuck state within minutes, not the next 06:00
health_watchdog.py run) as root.

Usage: python3 bin/monitoring/dq_dashboard_selfheal.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bin.core.notify import notify

UNIT = "dq-dashboard.service"


def main() -> int:
    is_failed = (
        subprocess.run(["systemctl", "is-failed", "--quiet", UNIT], timeout=10).returncode == 0
    )
    if not is_failed:
        return 0

    subprocess.run(["systemctl", "reset-failed", UNIT], timeout=10)
    start = subprocess.run(["systemctl", "start", UNIT], timeout=30)

    still_active = (
        subprocess.run(["systemctl", "is-active", "--quiet", UNIT], timeout=10).returncode == 0
    )

    if still_active:
        notify(f"[self-heal] {UNIT} was in failed (start-limit-hit) state, restarted OK.")
    else:
        notify(
            f"[self-heal] {UNIT} was failed and the restart attempt did NOT bring it "
            f"back (exit {start.returncode}) -- needs manual investigation."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
