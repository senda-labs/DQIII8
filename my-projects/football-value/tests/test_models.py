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
