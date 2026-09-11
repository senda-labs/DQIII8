#!/usr/bin/env python3
"""Telegram alert for a systemd service OnFailure= trigger.

Closes the "silent restart-loop for hours" gap found in the 2026-08-21
disaster-scenario sweep: health_watchdog only runs nightly, so a service
crash/restart loop during the day went undetected until the next run.
Wired as OnFailure=dqiii8-alert@%n.service on dqiii8-bot.service and
dq-dashboard.service (systemd unit changes, applied by a human -- see
02_hooks_and_permissions.md, /etc/systemd/ is a blocked write path).
"""

import sys

sys.path.insert(0, "/root/dqiii8")

from bin.core.notify import notify

if __name__ == "__main__":
    unit = sys.argv[1] if len(sys.argv) > 1 else "unknown unit"
    notify(f"DQIII8 service failure: {unit} entered a failed state (systemd OnFailure).")
