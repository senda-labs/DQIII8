"""
FBRef scraper — requests + BeautifulSoup4.
Rate limit: MINIMUM 4s between requests (ban-risk; high Cloudflare scrutiny).
Extracts xG, shots, corners, possession, fouls, cards from WC match reports.
Env: FBREF_DELAY_S (default 4.5)
"""
from __future__ import annotations

import logging
import os
import re
import time
import threading
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE = "https://fbref.com"
_SCHEDULE_URL = f"{_BASE}/en/comps/1/schedule/World-Cup-Scores-and-Fixtures"
_DELAY_S = float(os.getenv("FBREF_DELAY_S", "4.5"))

_USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

_last_request_ts: float = 0.0
_rate_lock = threading.Lock()


def _headers() -> dict:
    import random
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://fbref.com/",
    }


def _rate_limited_get(url: str) -> requests.Response:
    global _last_request_ts
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_ts
        if elapsed < _DELAY_S:
            time.sleep(_DELAY_S - elapsed)
        resp = requests.get(url, headers=_headers(), timeout=30)
        _last_request_ts = time.monotonic()
    resp.raise_for_status()
    return resp


def _norm_stat(value: str) -> float | int | None:
    """Parse a stat cell value: strip %, commas, return float or int. None if unparseable."""
    v = value.strip().rstrip("%").replace(",", "")
    if not v or v == "-":
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


# Maps FBRef stat label → (home_key, away_key) in our match_stats schema
_STAT_MAP: dict[str, tuple[str, str]] = {
    "Expected Goals (xG)":  ("home_xg",          "away_xg"),
    "xG":                   ("home_xg",          "away_xg"),
    "Total Shots":          ("home_shots",        "away_shots"),
    "Shots on Target":      ("home_sot",          "away_sot"),
    "Corners":              ("home_corners",      "away_corners"),
    "Possession":           ("home_possession",   "away_possession"),
    "Fouls":                ("home_fouls",        "away_fouls"),
    "Yellow Cards":         ("home_yellow",       "away_yellow"),
    "Red Cards":            ("home_red",          "away_red"),
}


def parse_match_stats(html: str) -> dict[str, Any]:
    """
    Parse the team_stats table from a FBRef match report page.
    Returns a dict with keys matching match_stats columns (home_xg, away_shots, ...).
    Returns {} if the table is absent or unparseable.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "team_stats"})
    if table is None:
        return {}

    stats: dict[str, Any] = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        label = cells[0].get_text(strip=True)
        if label not in _STAT_MAP:
            continue
        home_key, away_key = _STAT_MAP[label]
        home_val = _norm_stat(cells[1].get_text(strip=True))
        away_val = _norm_stat(cells[2].get_text(strip=True))
        if home_val is not None:
            stats[home_key] = home_val
        if away_val is not None:
            stats[away_key] = away_val

    return stats


def fetch_schedule() -> list[dict]:
    """
    Fetch WC2026 match schedule from FBRef.
    Returns list of {"fixture_id_hint": str, "date": str, "match_url": str | None}.
    The fixture_id_hint is a slug we attempt to match against our DB.
    """
    resp = _rate_limited_get(_SCHEDULE_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    matches = []
    for row in soup.select("table#sched_all tbody tr"):
        if "spacer" in row.get("class", []):
            continue
        date_cell = row.find("td", {"data-stat": "date"})
        score_cell = row.find("td", {"data-stat": "score"})
        home_cell = row.find("td", {"data-stat": "home_team"})
        away_cell = row.find("td", {"data-stat": "away_team"})
        if not (date_cell and score_cell and home_cell and away_cell):
            continue
        score_link = score_cell.find("a")
        match_url = (_BASE + score_link["href"]) if score_link else None
        matches.append({
            "date": date_cell.get_text(strip=True),
            "home": home_cell.get_text(strip=True),
            "away": away_cell.get_text(strip=True),
            "match_url": match_url,
        })
    return matches


def _find_fixture_id(conn, date_iso: str, home: str, away: str) -> str | None:
    """Match a FBRef game row to our canonical fixture by date + fuzzy team name."""
    home_n = home.lower().strip()
    away_n = away.lower().strip()
    rows = conn.execute(
        """SELECT f.id,
                  lower(coalesce(ht.name,'')) AS hn,
                  lower(coalesce(at.name,'')) AS an
           FROM fixtures f
           LEFT JOIN teams ht ON f.home_team_id = ht.id
           LEFT JOIN teams at ON f.away_team_id = at.id
           WHERE f.date = ?""",
        (date_iso,),
    ).fetchall()
    for row in rows:
        if row[1] == home_n and row[2] == away_n:
            return row[0]
        # partial match (e.g. "United States" vs "usa")
        if home_n in row[1] or row[1] in home_n:
            if away_n in row[2] or row[2] in away_n:
                return row[0]
    return None


def _fbref_date_to_iso(date_str: str) -> str | None:
    """
    Convert FBRef date string to ISO. FBRef uses formats like '2026-06-11'.
    Returns None if unparseable.
    """
    date_str = date_str.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str[:10]
    return None


def ingest(conn, fixture_ids: list[str] | None = None) -> int:
    """
    Scrape FBRef WC2026 schedule, fetch match reports for completed games,
    write xG/shots/corners/etc to match_stats. Skips fixtures already present.
    Returns total rows inserted.
    """
    from capture.store import write_match_stats, log_ingestion

    total = 0
    try:
        schedule = fetch_schedule()
    except Exception as exc:
        log_ingestion(conn, "fbref", status="failed", error_msg=f"schedule fetch failed: {exc}")
        return 0

    for item in schedule:
        date_iso = _fbref_date_to_iso(item["date"])
        if not date_iso or not item.get("match_url"):
            continue

        canonical_id = _find_fixture_id(conn, date_iso, item["home"], item["away"])
        if canonical_id is None:
            logger.debug("fbref: no fixture match for %s v %s on %s", item["home"], item["away"], date_iso)
            continue

        if fixture_ids is not None and canonical_id not in fixture_ids:
            continue

        # Skip if we already have fbref stats for this fixture
        existing = conn.execute(
            "SELECT 1 FROM match_stats WHERE fixture_id=? AND source='fbref'",
            (canonical_id,),
        ).fetchone()
        if existing:
            continue

        try:
            resp = _rate_limited_get(item["match_url"])
            stats = parse_match_stats(resp.text)
        except Exception as exc:
            logger.warning("fbref: %s failed: %s", item["match_url"], exc)
            log_ingestion(conn, "fbref", fixture_id=canonical_id, status="failed", error_msg=str(exc))
            continue

        if not stats:
            logger.debug("fbref: no stats parsed for %s", canonical_id)
            continue

        write_match_stats(conn, canonical_id, "fbref", stats)
        log_ingestion(conn, "fbref", fixture_id=canonical_id, status="ok", records_inserted=1)
        total += 1

    logger.info("fbref: inserted stats for %d fixtures", total)
    return total


async def fetch(client, query) -> None:
    return None  # synchronous scraper; use ingest() directly
