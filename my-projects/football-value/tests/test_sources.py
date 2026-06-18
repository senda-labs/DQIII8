import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_SAMPLE_WC_JSON = {
    "name": "World Cup 2026",
    "matches": [
        {
            "num": 1,
            "date": "Jun/11",
            "time": "18:00",
            "team1": {"name": "Mexico", "code": "MEX"},
            "team2": {"name": "Canada", "code": "CAN"},
            "score1": 2,
            "score2": 0,
            "group": "A",
            "stadium": {"name": "Estadio Azteca", "city": "Mexico City"}
        }
    ]
}

from capture.sources.openfootball import parse_wc_json, parse_wc_txt, parse_stadiums_csv

_SAMPLE_CUP_TXT = """\
▪ Group A
Thu June 11
  13:00 UTC-6     Mexico  2-0 (1-0)  South Africa        @ Mexico City
               (Julián Quiñones 9' Raúl Jiménez 67')
Thu June 18
  12:00 UTC-4     Czech Republic    v South Africa   @ Atlanta
"""

_SAMPLE_STADIUMS_CSV = """\
city,                  timezone,    cc,  name,                  capacity,   wikipedia, wikidata,     coords

Mexico City,           UTC-6, mx,  Estadio Azteca,     83000,    Estadio_Azteca,  Q320454,   19°18'11"N 99°09'02"W
"""


def test_parse_wc_txt_returns_completed_fixture():
    fixtures, teams, stadiums = parse_wc_txt(_SAMPLE_CUP_TXT, tournament="WC2026")
    completed = [f for f in fixtures if f["status"] == "completed"]
    assert len(completed) == 1
    assert completed[0]["home_score"] == 2
    assert completed[0]["away_score"] == 0
    assert completed[0]["stage"] == "Group A"


def test_parse_wc_txt_returns_scheduled_fixture():
    fixtures, teams, stadiums = parse_wc_txt(_SAMPLE_CUP_TXT, tournament="WC2026")
    scheduled = [f for f in fixtures if f["status"] == "scheduled"]
    assert len(scheduled) == 1
    assert scheduled[0]["home_score"] is None


def test_parse_wc_txt_extracts_teams():
    _, teams, _ = parse_wc_txt(_SAMPLE_CUP_TXT, tournament="WC2026")
    names = {t["name"] for t in teams}
    assert "Mexico" in names
    assert "South Africa" in names
    assert "Czech Republic" in names


def test_parse_stadiums_csv_decodes_dms_coords():
    stadiums = parse_stadiums_csv(_SAMPLE_STADIUMS_CSV)
    assert len(stadiums) == 1
    s = stadiums[0]
    assert s["id"] == "mexico_city"
    assert s["country"] == "MX"
    assert abs(s["lat"] - 19.303) < 0.01
    assert abs(s["lon"] - (-99.15)) < 0.01

def test_parse_wc_json_returns_fixtures():
    fixtures, teams, stadiums = parse_wc_json(_SAMPLE_WC_JSON, tournament="WC2026")
    assert len(fixtures) == 1
    f = fixtures[0]
    assert f["home_team_id"] == "MEX"
    assert f["away_team_id"] == "CAN"
    assert f["status"] == "completed"

def test_parse_wc_json_returns_teams():
    _, teams, _ = parse_wc_json(_SAMPLE_WC_JSON, tournament="WC2026")
    codes = {t["id"] for t in teams}
    assert "MEX" in codes
    assert "CAN" in codes

def test_parse_wc_json_returns_stadiums():
    _, _, stadiums = parse_wc_json(_SAMPLE_WC_JSON, tournament="WC2026")
    assert len(stadiums) >= 1
    assert stadiums[0]["city"] == "Mexico City"

def test_parse_wc_json_no_score_is_scheduled():
    data = {
        "matches": [{
            "date": "Jun/15",
            "team1": {"name": "France", "code": "FRA"},
            "team2": {"name": "Brazil", "code": "BRA"},
            "stadium": {"name": "MetLife", "city": "New York"},
        }]
    }
    fixtures, _, _ = parse_wc_json(data, tournament="WC2026")
    assert fixtures[0]["status"] == "scheduled"

# --- Task 9: statsbomb ---
from capture.sources.statsbomb import parse_statsbomb_event

# Shape matches statsbombpy's sb.events() flattened dataframe row (real format,
# not the raw nested StatsBomb open-data JSON): type/team/player are plain
# strings, outcome lives in a type-specific column (shot_outcome here).
_SAMPLE_EVENT = {
    "id": "evt-001",
    "index": 1,
    "minute": 34,
    "second": 12,
    "type": "Shot",
    "team": "France",
    "player": "Mbappé",
    "location": [88.3, 42.1],
    "shot_outcome": "Goal",
    "under_pressure": True,
}

def test_parse_statsbomb_event_maps_fields():
    result = parse_statsbomb_event("wc2022_f1", "FRA", _SAMPLE_EVENT)
    assert result["event_type"] == "Shot"
    assert result["minute"] == 34
    assert result["player_name"] == "Mbappé"
    assert result["under_pressure"] is True
    assert result["outcome"] == "Goal"

def test_parse_statsbomb_event_location():
    result = parse_statsbomb_event("wc2022_f1", "FRA", _SAMPLE_EVENT)
    assert abs(result["location_x"] - 88.3) < 0.001
    assert abs(result["location_y"] - 42.1) < 0.001

# --- Task 10: football_data ---
from capture.sources.football_data import parse_csv_row

_SAMPLE_ROW = {
    "HomeTeam": "Arsenal",
    "AwayTeam": "Chelsea",
    "FTHG": "2",
    "FTAG": "1",
    "HTHG": "1",
    "HTAG": "0",
    "HS": "15",
    "AS": "10",
    "HST": "6",
    "AST": "4",
    "HC": "7",
    "AC": "5",
    "HF": "12",
    "AF": "14",
    "B365H": "1.80",
    "B365D": "3.50",
    "B365A": "4.20",
}

def test_parse_csv_row_maps_stats():
    stats, odds = parse_csv_row(_SAMPLE_ROW)
    assert stats["home_score"] == 2
    assert stats["away_score"] == 1
    assert stats["home_shots"] == 15
    assert stats["home_corners"] == 7
    assert abs(odds["home_win"]["bet365"] - 1.80) < 0.001
    assert abs(odds["draw"]["bet365"] - 3.50) < 0.001

def test_parse_csv_row_empty_vals():
    stats, odds = parse_csv_row({"FTHG": "", "FTAG": "1"})
    assert "home_score" not in stats
    assert stats["away_score"] == 1

# --- Task 11: fifa_fdcp ---
from capture.sources.fifa_fdcp import parse_fixture, parse_scoreboard

_SAMPLE_FIXTURE = {
    "IdMatch": "400235455",
    "Home": {"IdTeam": "43942", "TeamName": [{"Locale": "en-GB", "Description": "Mexico"}]},
    "Away": {"IdTeam": "43923", "TeamName": [{"Locale": "en-GB", "Description": "Canada"}]},
    "Date": "2026-06-12T18:00:00Z",
    "Stadium": {"IdStadium": "stad_001", "Name": [{"Locale": "en-GB", "Description": "Test Stadium"}]},
    "ResultType": 1,
    "MatchStatus": 0,
    "StageName": [{"Locale": "en-GB", "Description": "Group A"}],
}

_SAMPLE_SCOREBOARD = {
    "HomeTeamScore": 2,
    "AwayTeamScore": 1,
    "MatchStatus": 3,
    "ResultType": 1,
    "BallPossession": {"OverallHome": 58.0, "OverallAway": 42.0},
    "Home": {},
    "Away": {},
}

def test_parse_fixture_maps_fields():
    fx = parse_fixture(_SAMPLE_FIXTURE, tournament="WC2026")
    assert fx["home_team_id"] == "43942"
    assert fx["away_team_id"] == "43923"
    assert fx["tournament"] == "WC2026"
    assert fx["id"] == "400235455"

def test_parse_scoreboard_maps_stats():
    stats = parse_scoreboard(_SAMPLE_SCOREBOARD)
    assert stats["home_score"] == 2
    assert stats["away_score"] == 1
    assert abs(stats["home_possession"] - 58.0) < 0.01

def test_parse_fixture_status_completed():
    # ResultType=1 → completed in v3 API
    raw = {**_SAMPLE_FIXTURE, "ResultType": 1, "MatchStatus": 0}
    fx = parse_fixture(raw, tournament="WC2026")
    assert fx["status"] == "completed"

def test_parse_fixture_status_live():
    raw = {**_SAMPLE_FIXTURE, "ResultType": 0, "MatchStatus": 3}
    fx = parse_fixture(raw, tournament="WC2026")
    assert fx["status"] == "live"

def test_parse_fixture_status_scheduled():
    raw = {**_SAMPLE_FIXTURE, "ResultType": 0, "MatchStatus": 1}
    fx = parse_fixture(raw, tournament="WC2026")
    assert fx["status"] == "scheduled"

# --- Task 12: api_football ---
from capture.sources.api_football import parse_fixture_response, parse_stats_response

_SAMPLE_FIXTURE_RESP = {
    "response": [{
        "fixture": {"id": 999, "date": "2026-06-12T18:00:00+00:00", "status": {"short": "FT"}},
        "teams": {
            "home": {"id": 1, "name": "Mexico", "winner": True},
            "away": {"id": 2, "name": "Canada", "winner": False},
        },
        "goals": {"home": 2, "away": 0},
        "score": {"halftime": {"home": 1, "away": 0}},
    }]
}

_SAMPLE_STATS_RESP = {
    "response": [
        {"statistics": [
            {"type": "Total Shots", "value": 15},
            {"type": "Shots on Goal", "value": 6},
            {"type": "Ball Possession", "value": "58%"},
        ]},
        {"statistics": [
            {"type": "Total Shots", "value": 8},
            {"type": "Shots on Goal", "value": 3},
            {"type": "Ball Possession", "value": "42%"},
        ]},
    ]
}

def test_parse_fixture_response():
    fixtures = parse_fixture_response(_SAMPLE_FIXTURE_RESP)
    assert len(fixtures) == 1
    assert fixtures[0]["home_score"] == 2
    assert fixtures[0]["ht_home_score"] == 1
    assert fixtures[0]["status"] == "completed"

def test_parse_stats_response_maps_possession():
    stats = parse_stats_response("999", _SAMPLE_STATS_RESP)
    assert stats["home_shots"] == 15
    assert abs(stats["home_possession"] - 58.0) < 0.01
    assert stats["away_shots"] == 8

# --- Task 13: betexplorer ---
from capture.sources.betexplorer import parse_odds_table, build_match_url

_SAMPLE_HTML = """
<table class="table-main">
<tr id="or-bet365" class="oc-tablerow">
  <td class="table-main__col table-main__doubleparameter">Bet365</td>
  <td class="table-main__col table-main__odd" data-odd="1.80">1.80</td>
  <td class="table-main__col table-main__odd" data-odd="3.50">3.50</td>
  <td class="table-main__col table-main__odd" data-odd="4.50">4.50</td>
</tr>
<tr id="or-pinnacle" class="oc-tablerow">
  <td class="table-main__col table-main__doubleparameter">Pinnacle</td>
  <td class="table-main__col table-main__odd" data-odd="1.75">1.75</td>
  <td class="table-main__col table-main__odd" data-odd="3.60">3.60</td>
  <td class="table-main__col table-main__odd" data-odd="4.80">4.80</td>
</tr>
</table>
"""

def test_parse_odds_table_extracts_rows():
    rows = parse_odds_table(_SAMPLE_HTML)
    assert len(rows) == 2
    bet365 = next(r for r in rows if r["bookmaker"] == "Bet365")
    assert abs(bet365["home_win"] - 1.80) < 0.001
    assert abs(bet365["draw"] - 3.50) < 0.001
    assert abs(bet365["away_win"] - 4.50) < 0.001

def test_parse_odds_table_both_bookmakers():
    rows = parse_odds_table(_SAMPLE_HTML)
    names = {r["bookmaker"] for r in rows}
    assert "Bet365" in names
    assert "Pinnacle" in names

def test_build_match_url_format():
    url = build_match_url("Mexico", "Canada", "2026-06-12")
    assert "mexico" in url
    assert "canada" in url
    assert "20260612" in url


# --- The Odds API ---
from capture.sources.the_odds_api import parse_odds_event, _commence_to_db_date, _norm_team

_SAMPLE_ODDS_EVENT = {
    "id": "evt-odds-001",
    "sport_key": "soccer_wc",
    "commence_time": "2026-06-11T18:00:00Z",
    "home_team": "Mexico",
    "away_team": "South Africa",
    "bookmakers": [
        {
            "key": "pinnacle",
            "title": "Pinnacle",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Mexico",       "price": 2.20},
                        {"name": "South Africa", "price": 4.00},
                        {"name": "Draw",         "price": 3.10},
                    ],
                }
            ],
        },
        {
            "key": "bet365",
            "title": "Bet365",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Mexico",       "price": 2.15},
                        {"name": "South Africa", "price": 4.10},
                        {"name": "Draw",         "price": 3.20},
                    ],
                }
            ],
        },
    ],
}

def test_parse_odds_event_date():
    result = parse_odds_event(_SAMPLE_ODDS_EVENT)
    assert result is not None
    assert result["date"] == "2026-06-11"

def test_parse_odds_event_teams():
    result = parse_odds_event(_SAMPLE_ODDS_EVENT)
    assert result["home_team"] == "Mexico"
    assert result["away_team"] == "South Africa"

def test_parse_odds_event_h2h_outcomes():
    result = parse_odds_event(_SAMPLE_ODDS_EVENT)
    rows = result["odds_rows"]
    # 2 bookmakers × 3 outcomes = 6 rows
    assert len(rows) == 6
    pinnacle_home = next(
        r for r in rows if r["bookmaker"] == "pinnacle" and r["outcome"] == "home_win"
    )
    assert abs(pinnacle_home["odds"] - 2.20) < 0.001
    assert pinnacle_home["market"] == "1x2"
    draw = next(r for r in rows if r["bookmaker"] == "pinnacle" and r["outcome"] == "draw")
    assert abs(draw["odds"] - 3.10) < 0.001

def test_parse_odds_event_empty_bookmakers():
    event = {**_SAMPLE_ODDS_EVENT, "bookmakers": []}
    result = parse_odds_event(event)
    assert result is not None
    assert result["odds_rows"] == []

def test_parse_odds_event_missing_fields():
    result = parse_odds_event({"id": "", "commence_time": "", "home_team": "", "away_team": ""})
    assert result is None

def test_commence_to_db_date():
    assert _commence_to_db_date("2026-06-11T18:00:00Z") == "2026-06-11"
    assert _commence_to_db_date("2026-07-01T21:00:00Z") == "2026-07-01"

def test_norm_team_aliases():
    assert _norm_team("United States") == "usa"
    assert _norm_team("México") != "usa"   # no alias → unchanged (lowercased)
    assert _norm_team("Mexico") == "mexico"
    assert _norm_team("Bosnia and Herzegovina") == "bosnia & herzegovina"

def test_parse_odds_event_totals():
    event = {
        "id": "e2",
        "commence_time": "2026-06-12T20:00:00Z",
        "home_team": "Canada",
        "away_team": "USA",
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "totals",
                "outcomes": [
                    {"name": "Over",  "price": 1.90, "point": 2.5},
                    {"name": "Under", "price": 1.95, "point": 2.5},
                ],
            }],
        }],
    }
    result = parse_odds_event(event)
    assert result is not None
    labels = {r["outcome"] for r in result["odds_rows"]}
    assert "over_2.5" in labels
    assert "under_2.5" in labels
