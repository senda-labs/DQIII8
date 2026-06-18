#!/usr/bin/env python3
"""
Daily capture script — runs all active sources in sequence.
Designed for cron: logs to stdout (redirect to file or systemd journal).
Exit code 0 if all sources succeed, 1 if any fail.

Usage:
    python3 scripts/daily_capture.py
    python3 scripts/daily_capture.py --skip-odds   # skip the_odds_api (rate budget)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no-op if file absent)."""
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("daily_capture")

_DB_PATH = ROOT / "database" / "football.db"


def _get_conn():
    from database.db_init import init_db, get_connection
    init_db(_DB_PATH)
    return get_connection(_DB_PATH)


def run_source(name: str, runner) -> bool:
    logger.info("=== %s: starting ===", name)
    try:
        n = runner()
        logger.info("=== %s: done — %d records ===", name, n)
        return True
    except Exception as exc:
        logger.error("=== %s: FAILED — %s ===", name, exc)
        return False


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Daily football data capture")
    parser.add_argument("--skip-odds", action="store_true", help="Skip the_odds_api call")
    args = parser.parse_args()

    conn = _get_conn()
    failures = 0

    # 1. FIFA FDCP — WC2026 fixtures + live scores
    import asyncio
    from capture.sources.fifa_fdcp import ingest as fifa_ingest
    if not run_source("fifa_fdcp", lambda: asyncio.run(fifa_ingest(conn))):
        failures += 1

    # 2. The Odds API — WC2026 pre-match odds (h2h + totals)
    #    500 req/month free tier: use once daily. Skipped if key not set.
    if not args.skip_odds:
        import os
        odds_key = os.getenv("THE_ODDS_API_KEY", "")
        if not odds_key:
            logger.warning("the_odds_api: THE_ODDS_API_KEY not set — skipping (add to .env)")
        else:
            from capture.sources.the_odds_api import ingest as odds_ingest
            sport = os.getenv("ODDS_API_SPORT", "soccer_wc")

            def _odds():
                return asyncio.run(odds_ingest(conn, sport=sport, markets="h2h,totals"))

            if not run_source("the_odds_api", _odds):
                failures += 1
    else:
        logger.info("=== the_odds_api: skipped (--skip-odds) ===")

    # 3. FBRef — xG + stats for completed WC2026 matches (rate-limited 4.5s/req)
    from capture.sources.fbref import ingest as fbref_ingest
    if not run_source("fbref", lambda: fbref_ingest(conn)):
        failures += 1

    conn.close()

    if failures:
        logger.error("daily_capture: %d source(s) failed", failures)
        return 1

    logger.info("daily_capture: all sources succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
