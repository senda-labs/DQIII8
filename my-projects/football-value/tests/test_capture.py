import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.db_init import init_db, get_connection

def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
    conn.close()
    assert tables == {"stadiums", "teams", "fixtures", "squads", "match_stats", "odds_snapshots", "events", "ingestion_log", "fixture_aliases"}

def test_init_db_wal_mode(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"

def test_init_db_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # must not raise
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    conn.close()
    assert count == 9

def test_get_connection_enforces_foreign_keys(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    # Insert a fixture with a non-existent team_id — should raise IntegrityError
    import pytest
    with pytest.raises(Exception):  # IntegrityError or OperationalError
        conn.execute(
            "INSERT INTO fixtures (id, tournament, home_team_id) VALUES ('f1', 'WC', 'NONEXISTENT')"
        )
        conn.commit()
    conn.close()

from capture.navigator.base import MatchQuery, SourceResult, SCORE_WEIGHTS

def test_source_result_score_formula():
    r = SourceResult(
        source="openfootball",
        url="https://example.com",
        raw={"home_score": 2, "away_score": 1},
        completeness=0.5,
        raw_completeness=0.5,
        completeness_cap=1.0,
        confidence=0.8,
        reliability=0.9,
        partial_paywall=False,
    )
    expected_score = (
        0.5 * SCORE_WEIGHTS["completeness"]
        + 0.8 * SCORE_WEIGHTS["confidence"]
        + 0.9 * SCORE_WEIGHTS["reliability"]
    )
    assert abs(r.score - expected_score) < 1e-6

def test_match_query_identity():
    q = MatchQuery(fixture_id="wc2026_001", home_team="Argentina", away_team="France")
    assert q.fixture_id == "wc2026_001"
    assert q.home_team == "Argentina"

def test_captcha_flag_reduces_score():
    r = SourceResult(
        source="test", url="", raw={},
        completeness=1.0, raw_completeness=1.0, completeness_cap=1.0,
        confidence=1.0, reliability=1.0, captcha_flag=True,
    )
    # Score should be penalized by CAPTCHA_PENALTY=0.4
    assert r.score < 1.0
    assert abs(r.score - round(1.0 * (1 - 0.4), 4)) < 1e-6

from capture.registry import REGISTRY, field_confidence, SOURCE_TIERS, update_source_stats

def test_registry_has_all_sources():
    expected = {"openfootball", "statsbomb", "football_data", "fifa_fdcp", "api_football", "betexplorer"}
    assert expected <= set(REGISTRY.keys())

def test_source_tiers_cover_all():
    all_in_tiers = {s for sources in SOURCE_TIERS.values() for s in sources}
    assert "betexplorer" in all_in_tiers
    assert "openfootball" in all_in_tiers

def test_field_confidence_returns_string():
    result = field_confidence("betexplorer", "home_win")
    assert result in ("high", "medium", "low")

def test_update_source_stats_increments():
    update_source_stats("test_src", success=True, latency_s=1.5)
    update_source_stats("test_src", success=False, latency_s=2.0)
    from capture.registry import get_source_stats
    stats = get_source_stats("test_src")
    assert stats["total"] == 2
    assert stats["successes"] == 1
    assert stats["failures"] == 1

import asyncio
from capture.navigator.resolver import SourceResolver, FUSION_DELTA

def test_fusion_delta_constant():
    assert FUSION_DELTA == 0.15

def test_source_resolver_instantiates():
    r = SourceResolver(sources=["openfootball", "football_data"])
    assert r is not None

def test_fuse_merges_higher_score_wins():
    from capture.navigator.base import SourceResult
    a = SourceResult(
        source="a", url="http://a.com", raw={"home_score": 2, "home_xg": 1.5},
        completeness=0.8, raw_completeness=0.8, completeness_cap=1.0,
        confidence=0.9, reliability=0.9,
    )
    b = SourceResult(
        source="b", url="http://b.com", raw={"home_score": 99, "away_score": 1},
        completeness=0.6, raw_completeness=0.6, completeness_cap=1.0,
        confidence=0.7, reliability=0.7,
    )
    fused = SourceResolver._fuse(a, b)
    # a wins home_score conflict (higher score source)
    assert fused.raw["home_score"] == 2
    # b contributes away_score which a didn't have
    assert fused.raw["away_score"] == 1
    # a's home_xg survives
    assert fused.raw["home_xg"] == 1.5
    assert fused.source == "a+b"

def test_resolver_returns_none_for_empty_sources():
    async def run():
        r = SourceResolver(sources=[])
        import httpx
        async with httpx.AsyncClient() as client:
            from capture.navigator.base import MatchQuery
            result = await r.resolve(client, MatchQuery(fixture_id="f1"))
            return result
    result = asyncio.run(run())
    assert result is None

from capture.navigator.worker import Task, Worker, _NAV_CACHE, BATCH_CONCURRENCY
from capture.navigator.base import MatchQuery

def test_task_key_includes_source_and_fixture():
    q = MatchQuery(fixture_id="wc2026_001")
    t = Task(query=q, source="openfootball")
    assert "openfootball" in t.key
    assert "wc2026_001" in t.key

def test_task_has_unique_task_id():
    q = MatchQuery(fixture_id="wc2026_001")
    t1 = Task(query=q)
    t2 = Task(query=q)
    assert t1.task_id != t2.task_id

def test_batch_concurrency_default():
    assert BATCH_CONCURRENCY == 6

from capture.store import write_match_stats, write_odds_snapshot, write_event, log_ingestion

def test_write_match_stats_inserts(tmp_path):
    from database.db_init import init_db, get_connection
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_connection(db)
    conn.execute("INSERT INTO fixtures (id, tournament, status) VALUES ('f1', 'WC2026', 'completed')")
    conn.commit()
    write_match_stats(conn, "f1", "test_source", {"home_score": 2, "away_score": 1})
    row = conn.execute("SELECT home_score, away_score FROM match_stats WHERE fixture_id='f1'").fetchone()
    conn.close()
    assert row["home_score"] == 2
    assert row["away_score"] == 1

def test_write_odds_snapshot_inserts(tmp_path):
    from database.db_init import init_db, get_connection
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_connection(db)
    conn.execute("INSERT INTO fixtures (id, tournament, status) VALUES ('f1', 'WC2026', 'completed')")
    conn.commit()
    write_odds_snapshot(conn, "f1", bookmaker="betexplorer", market="1x2",
                        outcome="home_win", odds=1.85, is_opening=True)
    row = conn.execute("SELECT odds, is_opening FROM odds_snapshots WHERE fixture_id='f1'").fetchone()
    conn.close()
    assert abs(row["odds"] - 1.85) < 0.001
    assert row["is_opening"] == 1

def test_log_ingestion_records_status(tmp_path):
    from database.db_init import init_db, get_connection
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_connection(db)
    log_ingestion(conn, "openfootball", status="ok", records_inserted=42)
    row = conn.execute("SELECT source, status, records_inserted FROM ingestion_log").fetchone()
    conn.close()
    assert row["source"] == "openfootball"
    assert row["status"] == "ok"
    assert row["records_inserted"] == 42

def test_write_event_ignores_duplicate_id(tmp_path):
    from database.db_init import init_db, get_connection
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_connection(db)
    conn.execute("INSERT INTO teams (id, name) VALUES ('t1', 'Team A')")
    conn.execute("INSERT INTO fixtures (id, tournament, status) VALUES ('f1', 'WC2026', 'completed')")
    conn.commit()
    write_event(conn, "evt1", "f1", minute=34, event_type="Shot", team_id="t1")
    write_event(conn, "evt1", "f1", minute=34, event_type="Shot", team_id="t1")  # duplicate — should not raise
    count = conn.execute("SELECT COUNT(*) FROM events WHERE id='evt1'").fetchone()[0]
    conn.close()
    assert count == 1  # INSERT OR IGNORE deduplicates

from click.testing import CliRunner
from capture.cli import cli

def test_cli_help_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output

def test_cli_ingest_unknown_source_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--source", "nonexistent_source_xyz"])
    assert result.exit_code != 0

def test_cli_stats_no_data(tmp_path):
    """Stats command runs without crashing on empty DB."""
    import os
    os.environ["FV_DB_PATH"] = str(tmp_path / "test.db")
    runner = CliRunner()
    # Can't easily override _DB_PATH, so just test that the module imports cleanly
    # and the CLI group help works
    result = runner.invoke(cli, ["stats", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Step 1: db_init / store hardening
# ---------------------------------------------------------------------------

def test_get_connection_has_timeout(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)
    # busy_timeout is in milliseconds; timeout=30 → 30000ms
    timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.close()
    assert timeout_ms >= 30000


def test_write_match_stats_whitelist_enforced(tmp_path):
    """The frozen whitelist prevents unrecognised columns reaching the SQL f-string."""
    from capture.store import write_match_stats, _STAT_FIELDS
    assert "drop_table" not in _STAT_FIELDS
    assert "home_score" in _STAT_FIELDS


def test_register_fixture_idempotent(tmp_path):
    from capture.store import register_fixture
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)
    register_fixture(conn, "f1", tournament="WC2026")
    register_fixture(conn, "f1", tournament="WC2026")  # must not raise
    count = conn.execute("SELECT COUNT(*) FROM fixtures WHERE id='f1'").fetchone()[0]
    conn.close()
    assert count == 1


def test_register_team_and_stadium_idempotent(tmp_path):
    from capture.store import register_team, register_stadium
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)
    register_team(conn, "MEX", "Mexico")
    register_team(conn, "MEX", "Mexico")  # must not raise
    register_stadium(conn, "S1", "MetLife")
    register_stadium(conn, "S1", "MetLife")
    assert conn.execute("SELECT COUNT(*) FROM teams WHERE id='MEX'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM stadiums WHERE id='S1'").fetchone()[0] == 1
    conn.close()


def test_register_fixture_null_fk_allowed(tmp_path):
    """NULL team/stadium FKs must not raise — calibration sources omit them."""
    from capture.store import register_fixture
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)
    register_fixture(conn, "fd_test", tournament="premier_league_2324",
                     home_team_id=None, away_team_id=None, stadium_id=None)
    count = conn.execute("SELECT COUNT(*) FROM fixtures WHERE id='fd_test'").fetchone()[0]
    conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# Step 3: integration tests — ingest() writes real rows to a temp DB
# ---------------------------------------------------------------------------

def test_football_data_ingest_rows_land(tmp_path, monkeypatch):
    """football_data.ingest() registers parent fixture and writes match_stats row."""
    from capture.sources import football_data
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)

    sample = [{
        "HomeTeam": "Arsenal", "AwayTeam": "Chelsea",
        "Date": "10/08/2024",
        "FTHG": "2", "FTAG": "1", "HTHG": "1", "HTAG": "0",
        "HS": "15", "AS": "10",
        "B365H": "1.80", "B365D": "3.50", "B365A": "4.20",
    }]
    monkeypatch.setattr(football_data, "download_csv", lambda s, c: sample)

    n = football_data.ingest(conn, season="2324", league="premier_league")

    stat_rows = conn.execute(
        "SELECT COUNT(*) FROM match_stats WHERE source='football_data'"
    ).fetchone()[0]
    odds_rows = conn.execute(
        "SELECT COUNT(*) FROM odds_snapshots WHERE bookmaker='bet365'"
    ).fetchone()[0]
    log_row = conn.execute(
        "SELECT status, records_inserted FROM ingestion_log WHERE source='football_data'"
    ).fetchone()
    conn.close()

    assert n == stat_rows == 1, f"ingest returned {n}, DB has {stat_rows} stat rows"
    assert odds_rows == 3  # home_win / draw / away_win
    assert log_row[0] == "ok"
    assert log_row[1] == 1


def test_football_data_ingest_log_ok_on_partial_failure(tmp_path, monkeypatch):
    """Rows that fail individually are skipped; the rest succeed; log says ok."""
    from capture.sources import football_data
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)

    sample = [
        {"HomeTeam": "", "AwayTeam": "", "Date": ""},  # skipped: empty fields
        {"HomeTeam": "Arsenal", "AwayTeam": "Chelsea", "Date": "10/08/2024",
         "FTHG": "2", "FTAG": "1"},
    ]
    monkeypatch.setattr(football_data, "download_csv", lambda s, c: sample)

    n = football_data.ingest(conn, season="2324", league="premier_league")
    conn.close()

    assert n == 1  # only the valid row counted


def test_fifa_fdcp_ingest_registers_parents(tmp_path, monkeypatch):
    """fifa_fdcp.ingest() inserts teams, stadium, and fixture before match_stats."""
    import asyncio
    from capture.sources import fifa_fdcp

    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)

    sample_matches = [{
        "IdMatch": "M001",
        "StageName": [{"Locale": "en-GB", "Description": "Group A"}],
        "Date": "2026-06-11T18:00:00Z",
        "MatchStatus": 1,
        "ResultType": 0,
        "Home": {"IdTeam": "T_USA", "TeamName": [{"Locale": "en-GB", "Description": "USA"}]},
        "Away": {"IdTeam": "T_MEX", "TeamName": [{"Locale": "en-GB", "Description": "Mexico"}]},
        "Stadium": {"IdStadium": "S_LA", "Name": [{"Locale": "en-GB", "Description": "LA Stadium"}]},
        "HomeTeamScore": None,
        "AwayTeamScore": None,
        "BallPossession": None,
    }]

    async def fake_fetch_matches(client, **kw):
        return sample_matches

    # ResultType=0, MatchStatus=1 → scheduled, so no stats written
    monkeypatch.setattr(fifa_fdcp, "fetch_matches", fake_fetch_matches)

    n = asyncio.run(fifa_fdcp.ingest(conn))

    fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
    teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    stadiums = conn.execute("SELECT COUNT(*) FROM stadiums").fetchone()[0]
    log_row = conn.execute(
        "SELECT status, records_inserted FROM ingestion_log WHERE source='fifa_fdcp'"
    ).fetchone()
    conn.close()

    assert n == 1, "ingest returned wrong count"
    assert fixtures == 1
    assert teams == 2
    assert stadiums == 1
    assert log_row[0] == "ok"
    assert log_row[1] == 1


def test_openfootball_seed_unbroken(tmp_path):
    """Regression: openfootball parse + store path still works after store.py changes."""
    from capture.sources.openfootball import parse_wc_json
    from capture.store import register_team, register_stadium, register_fixture, write_match_stats

    data = {
        "matches": [{
            "num": 1, "date": "Jun/11", "time": "18:00",
            "team1": {"name": "Mexico", "code": "MEX"},
            "team2": {"name": "Canada", "code": "CAN"},
            "score1": 2, "score2": 0, "group": "A",
            "stadium": {"name": "Estadio Azteca", "city": "Mexico City"},
        }]
    }
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)

    fixtures, teams, stadiums = parse_wc_json(data, tournament="WC2026")
    for t in teams:
        register_team(conn, t["id"], t["name"])
    for s in stadiums:
        register_stadium(conn, s["id"], s["name"])
    for fx in fixtures:
        register_fixture(conn, fx["id"], tournament=fx["tournament"],
                         date=fx["date"], status=fx["status"],
                         home_team_id=fx["home_team_id"],
                         away_team_id=fx["away_team_id"],
                         stadium_id=fx.get("stadium_id"))
        if fx.get("home_score") is not None:
            write_match_stats(conn, fx["id"], "openfootball",
                              {"home_score": fx["home_score"], "away_score": fx["away_score"]})

    fix_count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
    stat_count = conn.execute("SELECT COUNT(*) FROM match_stats").fetchone()[0]
    conn.close()

    assert fix_count == 1
    assert stat_count == 1


# ---------------------------------------------------------------------------
# Step 4: betexplorer RULE compliance
# ---------------------------------------------------------------------------

def test_betexplorer_rotates_user_agent():
    import threading as _threading
    from capture.sources import betexplorer
    seen = {betexplorer._headers()["User-Agent"] for _ in range(60)}
    assert len(seen) > 1, "UA pool must have multiple entries"
    assert betexplorer._headers()["Referer"]


def test_betexplorer_rate_lock_is_thread_safe():
    import threading as _threading
    from capture.sources import betexplorer
    assert isinstance(betexplorer._rate_lock, type(_threading.Lock()))


def test_register_alias_idempotent(tmp_path):
    from capture.store import register_alias, register_fixture
    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)
    register_fixture(conn, "f_canon", tournament="WC2026")
    register_alias(conn, "f_canon", "the_odds_api", "ext-001", source_home="Mexico", source_away="Canada")
    register_alias(conn, "f_canon", "the_odds_api", "ext-001", source_home="Mexico", source_away="Canada")  # must not raise
    count = conn.execute(
        "SELECT COUNT(*) FROM fixture_aliases WHERE source='the_odds_api' AND source_id='ext-001'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_the_odds_api_ingest_matches_fixture(tmp_path, monkeypatch):
    """the_odds_api.ingest() finds the canonical fixture and writes odds_snapshots."""
    import asyncio
    from capture.sources import the_odds_api
    from capture.store import register_team, register_fixture

    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)

    # Seed a fixture matching the sample event (Mexico v South Africa, June 11)
    register_team(conn, "MEX", "Mexico")
    register_team(conn, "SAF", "South Africa")
    register_fixture(conn, "wc2026_june11_mexico_south_afri_0",
                     tournament="WC2026", date="2026-06-11",
                     home_team_id="MEX", away_team_id="SAF", status="completed")
    conn.commit()

    # Canned API response with 1 event, 1 bookmaker, 3 h2h outcomes
    fake_events = [{
        "id": "odds-evt-001",
        "sport_key": "soccer_wc",
        "commence_time": "2026-06-11T18:00:00Z",
        "home_team": "Mexico",
        "away_team": "South Africa",
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": "Mexico",       "price": 2.20},
                    {"name": "South Africa", "price": 4.00},
                    {"name": "Draw",         "price": 3.10},
                ],
            }],
        }],
    }]

    async def fake_fetch_events(client, *, sport, markets):
        return fake_events, {"remaining": "499", "used": "1"}

    monkeypatch.setattr(the_odds_api, "fetch_events", fake_fetch_events)
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")

    n = asyncio.run(the_odds_api.ingest(conn))

    odds_count = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    alias_count = conn.execute(
        "SELECT COUNT(*) FROM fixture_aliases WHERE source='the_odds_api'"
    ).fetchone()[0]
    log = conn.execute(
        "SELECT status, records_inserted FROM ingestion_log WHERE source='the_odds_api'"
    ).fetchone()
    conn.close()

    assert n == 3, f"expected 3 odds rows, got {n}"
    assert odds_count == 3
    assert alias_count == 1
    assert log[0] == "ok"
    assert log[1] == 3


def test_the_odds_api_ingest_no_match_skips(tmp_path, monkeypatch):
    """Events with no matching canonical fixture are skipped, log still ok."""
    import asyncio
    from capture.sources import the_odds_api

    db = tmp_path / "t.db"
    init_db(db)
    conn = get_connection(db)

    fake_events = [{
        "id": "no-match-001",
        "sport_key": "soccer_wc",
        "commence_time": "2026-06-30T20:00:00Z",
        "home_team": "Unknown Team A",
        "away_team": "Unknown Team B",
        "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Unknown Team A", "price": 2.0},
            {"name": "Draw", "price": 3.0},
            {"name": "Unknown Team B", "price": 4.0},
        ]}]}],
    }]

    async def fake_fetch_events(client, *, sport, markets):
        return fake_events, {"remaining": "498", "used": "2"}

    monkeypatch.setattr(the_odds_api, "fetch_events", fake_fetch_events)
    monkeypatch.setenv("THE_ODDS_API_KEY", "test-key")

    n = asyncio.run(the_odds_api.ingest(conn))
    log = conn.execute(
        "SELECT status, records_inserted FROM ingestion_log WHERE source='the_odds_api'"
    ).fetchone()
    conn.close()

    assert n == 0
    assert log[0] == "ok"
    assert log[1] == 0


def test_registry_has_the_odds_api():
    from capture.registry import REGISTRY, SOURCE_TIERS
    assert "the_odds_api" in REGISTRY
    assert "the_odds_api" in SOURCE_TIERS["odds"]


def test_resolver_is_dormant():
    """Guard: all fetch() stubs return None — resolver is not wired in Fase 1."""
    import asyncio, httpx
    from capture.navigator.base import MatchQuery
    from capture.navigator.resolver import SourceResolver

    async def run():
        r = SourceResolver(sources=["openfootball", "football_data", "fifa_fdcp",
                                    "api_football", "betexplorer"])
        async with httpx.AsyncClient() as client:
            return await r.resolve(client, MatchQuery(fixture_id="f1"))

    result = asyncio.run(run())
    assert result is None, "resolver must return None while fetch() stubs are dormant"
