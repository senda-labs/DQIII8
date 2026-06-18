"""
The Odds API — multi-bookmaker odds aggregator (https://the-odds-api.com/).
Free tier: 500 req/month. API key via THE_ODDS_API_KEY env var.

Provides H2H (1x2) + totals from 40+ bookmakers including Pinnacle via aggregation.
Official REST API — no scraping, no anti-ban risk.

Sport key: configurable via ODDS_API_SPORT env var (default: soccer_wc).
Regions:   EU bookmakers (Pinnacle, bet365, Unibet, etc.)
Markets:   h2h (1X2 for football). Extend to totals in Fase 2.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.the-odds-api.com/v4"
_DEFAULT_SPORT = os.getenv("ODDS_API_SPORT", "soccer_wc")
_REGIONS = "eu"

# Team name aliases: maps The Odds API names → canonical names in our teams table.
# Both the API name and the DB name are lowercased before lookup, so keys here
# are lowercased Odds API strings; values are lowercased DB names.
# WC2026 DB uses FIFA FDCP naming (Czechia, Korea Republic, Türkiye, etc.)
_TEAM_ALIASES: dict[str, str] = {
    # USA variants
    "united states": "usa",
    "us": "usa",
    # Ireland
    "republic of ireland": "ireland",
    # Ivory Coast
    "côte d'ivoire": "ivory coast",
    "cote d'ivoire": "ivory coast",
    # Korea — Odds API uses "South Korea", FIFA FDCP uses "Korea Republic"
    "south korea": "korea republic",
    # Czechia — Odds API uses "Czech Republic", FIFA FDCP uses "Czechia"
    "czech republic": "czechia",
    # Turkey — Odds API uses "Turkey", FIFA FDCP uses "Türkiye"
    "turkey": "türkiye",
    "turkiye": "türkiye",   # ASCII fallback
    # Iran — Odds API uses "Iran", FIFA FDCP uses "IR Iran"
    "iran": "ir iran",
    # Cape Verde — Odds API uses "Cape Verde", FIFA FDCP uses "Cabo Verde"
    "cape verde": "cabo verde",
    # DR Congo — Odds API uses "DR Congo", FIFA FDCP uses "Congo DR"
    "dr congo": "congo dr",
    # North Macedonia / North Korea
    "north macedonia": "north macedonia",
    "dpr korea": "north korea",
    # Bosnia
    "bosnia and herzegovina": "bosnia and herzegovina",
    "bosnia & herzegovina": "bosnia and herzegovina",
}


def _get_key() -> str:
    key = os.getenv("THE_ODDS_API_KEY", "")
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY env var not set")
    return key


def _commence_to_db_date(commence_time: str) -> str:
    """Convert ISO datetime '2026-06-11T18:00:00Z' → '2026-06-11' (ISO date, matches fixtures.date)."""
    dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")


def _norm_team(name: str) -> str:
    """Normalise a team name for fuzzy matching against our teams table."""
    n = name.lower().strip()
    return _TEAM_ALIASES.get(n, n)


def parse_odds_event(event: dict) -> dict[str, Any] | None:
    """
    Parse one Odds API event into a structured dict.

    Returns:
        {
          "event_id": str,
          "date": str,          # "2026-06-11" format (ISO date, matches fixtures.date)
          "home_team": str,     # raw name from API
          "away_team": str,     # raw name from API
          "odds_rows": [        # flat list ready for write_odds_snapshot
            {"bookmaker": str, "market": str, "outcome": str, "odds": float}
          ]
        }
    or None if the event has no bookmakers / cannot be parsed.
    """
    event_id = event.get("id", "")
    commence = event.get("commence_time", "")
    home = event.get("home_team", "")
    away = event.get("away_team", "")

    if not (event_id and commence and home and away):
        return None

    try:
        date_str = _commence_to_db_date(commence)
    except (ValueError, TypeError):
        logger.warning("the_odds_api: cannot parse commence_time %r", commence)
        return None

    odds_rows: list[dict] = []
    for bk in event.get("bookmakers", []):
        bookmaker = bk.get("key", "")
        for mkt in bk.get("markets", []):
            market_key = mkt.get("key", "")
            if market_key == "h2h":
                market = "1x2"
                for oc in mkt.get("outcomes", []):
                    name = oc.get("name", "")
                    price = oc.get("price")
                    if price is None:
                        continue
                    if name.lower() == "draw":
                        outcome = "draw"
                    elif name.lower() == home.lower():
                        outcome = "home_win"
                    elif name.lower() == away.lower():
                        outcome = "away_win"
                    else:
                        logger.debug("the_odds_api: unmapped h2h outcome %r", name)
                        continue
                    odds_rows.append({"bookmaker": bookmaker, "market": market,
                                      "outcome": outcome, "odds": float(price)})
            elif market_key == "totals":
                market = "totals"
                for oc in mkt.get("outcomes", []):
                    name = oc.get("name", "").lower()
                    price = oc.get("price")
                    point = oc.get("point")
                    if price is None or point is None:
                        continue
                    label = f"over_{point}" if name == "over" else f"under_{point}"
                    odds_rows.append({"bookmaker": bookmaker, "market": market,
                                      "outcome": label, "odds": float(price)})

    return {
        "event_id": event_id,
        "date": date_str,
        "home_team": home,
        "away_team": away,
        "odds_rows": odds_rows,
    }


def _find_canonical(conn, date_str: str, home: str, away: str) -> str | None:
    """
    Find a canonical fixture_id by matching date + team names.
    Compares normalised lower-case team names against our teams table.
    Returns None if no match — does NOT create orphan fixtures.
    """
    home_n = _norm_team(home)
    away_n = _norm_team(away)

    rows = conn.execute(
        """
        SELECT f.id,
               lower(coalesce(ht.name, '')) AS hn,
               lower(coalesce(at.name, '')) AS an
        FROM fixtures f
        LEFT JOIN teams ht ON f.home_team_id = ht.id
        LEFT JOIN teams at ON f.away_team_id = at.id
        WHERE f.date = ?
        """,
        (date_str,),
    ).fetchall()

    for row in rows:
        rh = _norm_team(row["hn"])
        ra = _norm_team(row["an"])
        if rh == home_n and ra == away_n:
            return row["id"]

    return None


async def fetch_events(
    client: httpx.AsyncClient,
    *,
    sport: str = _DEFAULT_SPORT,
    markets: str = "h2h",
) -> tuple[list[dict], dict]:
    """
    Fetch all upcoming events + odds for a sport.
    Returns (events_list, rate_info) where rate_info contains remaining/used counts.
    """
    key = _get_key()
    resp = await client.get(
        f"{_BASE}/sports/{sport}/odds/",
        params={
            "apiKey": key,
            "regions": _REGIONS,
            "markets": markets,
            "oddsFormat": "decimal",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    rate_info = {
        "remaining": resp.headers.get("x-requests-remaining", "?"),
        "used": resp.headers.get("x-requests-used", "?"),
    }
    return resp.json(), rate_info


async def ingest(
    conn,
    *,
    sport: str = _DEFAULT_SPORT,
    markets: str = "h2h",
    is_opening: bool = False,
    is_closing: bool = False,
) -> int:
    """
    Fetch current pre-match odds and write to odds_snapshots.
    Matches events to canonical fixtures by date + team name.
    Returns number of odds snapshots inserted.

    is_opening / is_closing: caller tags the snapshot type (default: neither —
    a mid-market capture). Set is_closing=True for the last snapshot before kickoff.
    """
    from capture.store import register_alias, write_odds_snapshot, log_ingestion

    try:
        _get_key()
    except RuntimeError as exc:
        log_ingestion(conn, "the_odds_api", status="failed", error_msg=str(exc))
        return 0

    async with httpx.AsyncClient() as client:
        try:
            raw_events, rate_info = await fetch_events(client, sport=sport, markets=markets)
        except Exception as exc:
            log_ingestion(conn, "the_odds_api", status="failed", error_msg=str(exc))
            return 0

        logger.info(
            "the_odds_api: %s events fetched — %s requests remaining (%s used)",
            len(raw_events), rate_info["remaining"], rate_info["used"],
        )

        total = 0
        unmatched = 0

        for raw in raw_events:
            parsed = parse_odds_event(raw)
            if not parsed or not parsed["odds_rows"]:
                continue

            canonical_id = _find_canonical(
                conn, parsed["date"], parsed["home_team"], parsed["away_team"],
            )
            if canonical_id is None:
                logger.warning(
                    "the_odds_api: no canonical fixture for %s v %s on %s — skipped",
                    parsed["home_team"], parsed["away_team"], parsed["date"],
                )
                unmatched += 1
                continue

            # Register the alias so future ingests can skip the fuzzy match
            register_alias(
                conn, canonical_id, "the_odds_api", parsed["event_id"],
                source_home=parsed["home_team"], source_away=parsed["away_team"],
            )

            for row in parsed["odds_rows"]:
                try:
                    write_odds_snapshot(
                        conn, canonical_id,
                        bookmaker=row["bookmaker"],
                        market=row["market"],
                        outcome=row["outcome"],
                        odds=row["odds"],
                        is_opening=is_opening,
                        is_closing=is_closing,
                    )
                    total += 1
                except Exception as exc:
                    logger.warning(
                        "the_odds_api: write_odds_snapshot failed for %s/%s: %s",
                        canonical_id, row["outcome"], exc,
                    )

        if unmatched:
            logger.warning("the_odds_api: %d events had no canonical fixture match", unmatched)

        conn.commit()
        log_ingestion(conn, "the_odds_api", status="ok", records_inserted=total)
        logger.info("the_odds_api: %d odds snapshots inserted (%d unmatched)", total, unmatched)
        return total


async def fetch(client: httpx.AsyncClient, query) -> None:
    return None  # use ingest() directly; resolver DORMANT until Fase 4
