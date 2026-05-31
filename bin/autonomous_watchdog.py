#!/usr/bin/env python3
"""bin/autonomous_watchdog.py — Watchdog supervisor for autonomous_loop.sh.

Launched in background by autonomous_loop.sh. Monitors:
  1. Parent process liveness — alerts if loop dies without cleanup trap firing.
  2. Heartbeat file staleness — alerts if loop hangs for > HANG_TIMEOUT seconds
     without starting a new cycle.

The main loop writes tasks/autonomous_heartbeat.txt at the start of each cycle.
"""
import os
import sys
import time
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
sys.path.insert(0, str(DQIII8_ROOT))

from bin.core.notify import notify  # type: ignore

HEARTBEAT_FILE = DQIII8_ROOT / "tasks" / "autonomous_heartbeat.txt"
CHECK_INTERVAL = 60    # seconds between checks
HANG_TIMEOUT   = 1800  # 30 min without a new cycle → alert


def _parent_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but different uid


def main() -> None:
    parent_pid = os.getppid()
    hang_alerted = False

    while True:
        time.sleep(CHECK_INTERVAL)

        if not _parent_alive(parent_pid):
            notify(
                f"[DQIII8] Watchdog: sesión autónoma terminó sin cleanup"
                f" (PID {parent_pid}). Revisar estado del loop."
            )
            break

        if not HEARTBEAT_FILE.exists():
            continue

        age = time.time() - HEARTBEAT_FILE.stat().st_mtime
        if age > HANG_TIMEOUT and not hang_alerted:
            notify(
                f"[DQIII8] Watchdog: loop sin actividad {int(age / 60)} min"
                " — posible cuelgue. Revisar tmux dqiii8."
            )
            hang_alerted = True
        elif age < HANG_TIMEOUT and hang_alerted:
            hang_alerted = False  # loop recovered, reset alert flag


if __name__ == "__main__":
    main()
