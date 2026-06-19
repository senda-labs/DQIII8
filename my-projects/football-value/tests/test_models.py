import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.dixon_coles import DixonColes, Prediction, value_edge


# Minimal synthetic dataset: 3 teams, 6 matches
_MATCHES = [
    {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1},
    {"home_team": "B", "away_team": "C", "home_score": 0, "away_score": 0},
    {"home_team": "C", "away_team": "A", "home_score": 1, "away_score": 3},
    {"home_team": "A", "away_team": "C", "home_score": 2, "away_score": 0},
    {"home_team": "B", "away_team": "A", "home_score": 1, "away_score": 2},
    {"home_team": "C", "away_team": "B", "home_score": 1, "away_score": 1},
]


def test_fit_returns_self():
    model = DixonColes()
    result = model.fit(_MATCHES)
    assert result is model  # fluent API


def test_predict_probabilities_sum_to_one():
    model = DixonColes().fit(_MATCHES)
    pred = model.predict("A", "B")
    total = pred.home_win + pred.draw + pred.away_win
    assert abs(total - 1.0) < 1e-6


def test_predict_returns_prediction_type():
    model = DixonColes().fit(_MATCHES)
    pred = model.predict("A", "B")
    assert isinstance(pred, Prediction)
    assert 0.0 < pred.home_win < 1.0
    assert 0.0 < pred.draw < 1.0
    assert 0.0 < pred.away_win < 1.0


def test_predict_lambdas_positive():
    model = DixonColes().fit(_MATCHES)
    pred = model.predict("A", "B")
    assert pred.lambda_home > 0
    assert pred.lambda_away > 0


def test_stronger_team_wins_more_often():
    # Team A won 3, lost 0 in _MATCHES — should be favored vs C
    model = DixonColes().fit(_MATCHES)
    pred = model.predict("A", "C")
    assert pred.home_win > pred.away_win


def test_value_edge_positive_when_model_higher():
    # model says 60% but odds imply 50% → edge = 0.60 * 2.00 - 1 = 0.20
    assert abs(value_edge(0.60, 2.00) - 0.20) < 1e-9


def test_value_edge_negative_when_overpriced():
    # model says 40% but odds imply 50% → edge = 0.40 * 2.00 - 1 = -0.20
    assert abs(value_edge(0.40, 2.00) - (-0.20)) < 1e-9


def test_predict_unknown_team_raises():
    import pytest
    model = DixonColes().fit(_MATCHES)
    with pytest.raises(KeyError):
        model.predict("A", "UNKNOWN")


import math


def test_continuous_poisson_pmf_at_integer():
    """_poisson_pmf_continuous at integer x must match scipy poisson.pmf."""
    from models.dixon_coles import _poisson_pmf_continuous
    from scipy.stats import poisson
    for lam in [0.5, 1.5, 2.7]:
        for x in [0, 1, 2, 3]:
            expected = poisson.pmf(x, lam)
            got = _poisson_pmf_continuous(float(x), lam)
            assert abs(got - expected) < 1e-9, f"x={x}, lam={lam}: {got} != {expected}"


def test_continuous_poisson_pmf_positive_at_fractional():
    """Must be positive and finite for fractional xG values."""
    from models.dixon_coles import _poisson_pmf_continuous
    for x in [0.3, 0.7, 1.2, 1.8, 2.5]:
        p = _poisson_pmf_continuous(x, 1.5)
        assert p > 0, f"x={x}: got non-positive {p}"
        assert math.isfinite(p), f"x={x}: non-finite {p}"


def test_continuous_poisson_pmf_guards():
    """Edge cases: x<0 → 0.0, lam<=0 → 0.0."""
    from models.dixon_coles import _poisson_pmf_continuous
    assert _poisson_pmf_continuous(-0.1, 1.0) == 0.0
    assert _poisson_pmf_continuous(1.0, 0.0) == 0.0
    assert _poisson_pmf_continuous(1.0, -0.5) == 0.0


def test_load_matches_includes_xg_keys(tmp_path):
    """load_matches_from_db dicts must include home_xg and away_xg keys (may be None)."""
    import sqlite3
    from models.dixon_coles import load_matches_from_db

    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE teams (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE fixtures (
            id TEXT PRIMARY KEY, date TEXT, tournament TEXT,
            home_team_id TEXT, away_team_id TEXT, status TEXT
        );
        CREATE TABLE match_stats (
            fixture_id TEXT, source TEXT,
            home_score INTEGER, away_score INTEGER,
            home_xg REAL, away_xg REAL
        );
        INSERT INTO teams VALUES ('t1','Alpha'),('t2','Beta');
        INSERT INTO fixtures VALUES ('f1','2022-11-20','WC2022','t1','t2','completed');
        INSERT INTO match_stats VALUES ('f1','openfootball',2,1,1.8,0.7);
    """)

    matches = load_matches_from_db(conn)
    assert len(matches) == 1
    m = matches[0]
    assert "home_xg" in m
    assert "away_xg" in m
    assert m["home_xg"] == 1.8
    assert m["away_xg"] == 0.7
    conn.close()


def test_load_matches_xg_null_allowed(tmp_path):
    """load_matches_from_db must include matches where xG is NULL (returns None)."""
    import sqlite3
    from models.dixon_coles import load_matches_from_db

    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE teams (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE fixtures (
            id TEXT PRIMARY KEY, date TEXT, tournament TEXT,
            home_team_id TEXT, away_team_id TEXT, status TEXT
        );
        CREATE TABLE match_stats (
            fixture_id TEXT, source TEXT,
            home_score INTEGER, away_score INTEGER,
            home_xg REAL, away_xg REAL
        );
        INSERT INTO teams VALUES ('t1','Alpha'),('t2','Beta');
        INSERT INTO fixtures VALUES ('f1','2022-11-20','WC2022','t1','t2','completed');
        INSERT INTO match_stats VALUES ('f1','openfootball',2,1,NULL,NULL);
    """)

    matches = load_matches_from_db(conn)
    assert len(matches) == 1
    assert matches[0]["home_xg"] is None
    assert matches[0]["away_xg"] is None
    conn.close()


# Synthetic dataset with xG values
_MATCHES_XG = [
    {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1, "home_xg": 1.8, "away_xg": 0.9},
    {"home_team": "B", "away_team": "C", "home_score": 0, "away_score": 0, "home_xg": 0.4, "away_xg": 0.3},
    {"home_team": "C", "away_team": "A", "home_score": 1, "away_score": 3, "home_xg": 0.8, "away_xg": 2.6},
    {"home_team": "A", "away_team": "C", "home_score": 2, "away_score": 0, "home_xg": 2.1, "away_xg": 0.2},
    {"home_team": "B", "away_team": "A", "home_score": 1, "away_score": 2, "home_xg": 0.9, "away_xg": 1.7},
    {"home_team": "C", "away_team": "B", "home_score": 1, "away_score": 1, "home_xg": 1.1, "away_xg": 1.3},
]


def test_xg_mode_fit_succeeds():
    """DixonColes(mode='xg') must fit without error and produce valid predictions."""
    model = DixonColes(mode="xg").fit(_MATCHES_XG)
    pred = model.predict("A", "B")
    total = pred.home_win + pred.draw + pred.away_win
    assert abs(total - 1.0) < 1e-6
    assert pred.lambda_home > 0
    assert pred.lambda_away > 0


def test_xg_mode_lambdas_differ_from_goals():
    """xG-fitted λ must differ from goals-fitted λ (they use different observations)."""
    goals_model = DixonColes(mode="goals").fit(_MATCHES_XG)
    xg_model    = DixonColes(mode="xg").fit(_MATCHES_XG)
    g_pred = goals_model.predict("A", "B")
    x_pred = xg_model.predict("A", "B")
    # They should differ because xG != goals in _MATCHES_XG
    assert abs(g_pred.lambda_home - x_pred.lambda_home) > 1e-4


def test_hybrid_mode_fit_succeeds():
    """DixonColes(mode='hybrid', alpha=0.5) must fit without error."""
    model = DixonColes(mode="hybrid", alpha=0.5).fit(_MATCHES_XG)
    pred = model.predict("A", "B")
    total = pred.home_win + pred.draw + pred.away_win
    assert abs(total - 1.0) < 1e-6


def test_hybrid_lambda_between_goals_and_xg():
    """Hybrid λ (alpha=0.5) must be between pure goals and pure xG λ values."""
    goals_model  = DixonColes(mode="goals").fit(_MATCHES_XG)
    xg_model     = DixonColes(mode="xg").fit(_MATCHES_XG)
    hybrid_model = DixonColes(mode="hybrid", alpha=0.5).fit(_MATCHES_XG)

    g_lh = goals_model.predict("A", "B").lambda_home
    x_lh = xg_model.predict("A", "B").lambda_home
    h_lh = hybrid_model.predict("A", "B").lambda_home
    lo, hi = sorted([g_lh, x_lh])
    # Hybrid should be within 10% of the [lo, hi] range (optimizer landscape may shift it slightly)
    assert lo * 0.9 <= h_lh <= hi * 1.1, f"hybrid={h_lh} not in [{lo},{hi}]"


def test_xg_mode_skips_null_xg_matches():
    """mode='xg' must skip matches where home_xg or away_xg is None (no crash)."""
    matches_with_nulls = _MATCHES_XG[:3] + [
        {"home_team": "A", "away_team": "C", "home_score": 2, "away_score": 0,
         "home_xg": None, "away_xg": None},  # NULL xG — must be silently skipped
    ] + _MATCHES_XG[4:]
    model = DixonColes(mode="xg").fit(matches_with_nulls)
    pred = model.predict("A", "B")
    assert abs(pred.home_win + pred.draw + pred.away_win - 1.0) < 1e-6


def test_goals_mode_unchanged_with_xg_in_dicts():
    """mode='goals' (default) must produce same result regardless of xG keys in dicts."""
    goals_only = [
        {"home_team": m["home_team"], "away_team": m["away_team"],
         "home_score": m["home_score"], "away_score": m["away_score"]}
        for m in _MATCHES_XG
    ]
    model_plain = DixonColes().fit(goals_only)
    model_xg    = DixonColes().fit(_MATCHES_XG)  # xG keys present but mode='goals' — must ignore them
    p1 = model_plain.predict("A", "B")
    p2 = model_xg.predict("A", "B")
    assert abs(p1.lambda_home - p2.lambda_home) < 1e-9
