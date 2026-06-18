"""
Dixon-Coles bivariate Poisson goals model (Dixon & Coles 1997).

Adds ρ-correction to independent Poisson, inflating 0-0 / 1-0 / 0-1 / 1-1
joint probabilities. These are the low-score outcomes that independent Poisson
under-estimates — exactly the tail where clean-sheet / Under / BTTS-no markets live.

Parameters (per fit):
  attack[team], defense[team], home_adv (scalar), rho (scalar, typically negative)
  lambda_home = exp(home_adv + attack[home] + defense[away])
  lambda_away = exp(attack[away] + defense[home])
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    home_win: float
    draw: float
    away_win: float
    lambda_home: float
    lambda_away: float


def value_edge(model_prob: float, bookmaker_odds: float) -> float:
    """Expected value per unit staked: model_prob * odds - 1. Positive = value bet."""
    return model_prob * bookmaker_odds - 1.0


def _tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles correction for joint probability P(x, y) when x+y <= 1."""
    if x == 0 and y == 0:
        return 1 - lh * la * rho
    if x == 1 and y == 0:
        return 1 + la * rho
    if x == 0 and y == 1:
        return 1 + lh * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def _joint_prob(x: int, y: int, lh: float, la: float, rho: float) -> float:
    """P(home=x, away=y) under Dixon-Coles model."""
    t = _tau(x, y, lh, la, rho)
    p = poisson.pmf(x, lh) * poisson.pmf(y, la) * t
    if p <= 0:
        return 1e-10  # tau went negative — log-likelihood will penalize this region
    return p


class DixonColes:
    """
    Bivariate Poisson goals model with ρ-correction.

    Usage:
        model = DixonColes().fit(matches)
        pred = model.predict("Switzerland", "Bosnia & Herzegovina")
        edge = value_edge(pred.home_win, 2.10)
    """

    def __init__(self) -> None:
        self._attack: dict[str, float] = {}
        self._defense: dict[str, float] = {}
        self._home_adv: float = 0.0
        self._rho: float = 0.0
        self._fitted: bool = False

    def fit(self, matches: list[dict[str, Any]]) -> "DixonColes":
        """
        Fit on a list of completed matches.
        Each match: {"home_team": str, "away_team": str, "home_score": int, "away_score": int}
        """
        teams = sorted({m["home_team"] for m in matches} | {m["away_team"] for m in matches})
        n = len(teams)
        idx = {t: i for i, t in enumerate(teams)}

        if len(matches) < n * 2:
            logger.warning(
                "DixonColes: only %d matches for %d teams — fit may be unreliable (need >= %d)",
                len(matches), n, n * 2,
            )

        # Initial params: [attack×n, defense×n, home_adv, rho]
        # Identifiability: constrain attack[0]=0 via SLSQP equality. Defense is left free
        # (conventional Dixon-Coles parameterization; attack sum-to-zero is not required).
        x0 = np.zeros(2 * n + 2)
        x0[-2] = 0.3   # home advantage prior
        x0[-1] = -0.1  # rho prior (negative = low-score inflation)

        def neg_log_likelihood(params: np.ndarray) -> float:
            attack  = params[:n]
            defense = params[n:2*n]
            home_adv = params[-2]
            rho = params[-1]
            ll = 0.0
            for m in matches:
                i_h = idx[m["home_team"]]
                i_a = idx[m["away_team"]]
                lh = math.exp(home_adv + attack[i_h] + defense[i_a])
                la = math.exp(attack[i_a] + defense[i_h])
                ll += math.log(_joint_prob(int(m["home_score"]), int(m["away_score"]), lh, la, rho))
            return -ll

        # Bounds on attack/defense to keep lambdas sane on sparse datasets
        # attack/defense in (-3, 3) → lambda range exp(-6)..exp(6+3) ≈ 0.002..8103
        bounds = [(-3.0, 3.0)] * (2 * n) + [(-2.0, 2.0), (-0.5, 0.5)]  # home_adv, rho

        # Constraints: attack[0] = 0 (fix one team as baseline for identifiability)
        constraints = [{"type": "eq", "fun": lambda p: p[0]}]
        result = minimize(
            neg_log_likelihood, x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-9},
        )

        if not result.success:
            logger.warning(
                "DixonColes optimizer did not converge (n=%d matches, %d teams): %s",
                len(matches), n, result.message,
            )

        params = result.x
        for t in teams:
            self._attack[t]  = params[idx[t]]
            self._defense[t] = params[n + idx[t]]
        self._home_adv = params[-2]
        self._rho = params[-1]
        self._fitted = True
        return self

    def _lambdas(self, home: str, away: str) -> tuple[float, float]:
        lh = math.exp(self._home_adv + self._attack[home] + self._defense[away])
        la = math.exp(self._attack[away] + self._defense[home])
        return lh, la

    def predict(self, home: str, away: str, max_goals: int = 8) -> Prediction:
        """
        Predict match outcome probabilities under the Dixon-Coles model.
        Raises KeyError if either team was not seen during fit().
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted — call fit() first")
        # KeyError propagates naturally if team unknown — caller's responsibility
        lh, la = self._lambdas(home, away)

        home_win = draw = away_win = 0.0
        for x in range(max_goals + 1):
            for y in range(max_goals + 1):
                p = _joint_prob(x, y, lh, la, self._rho)
                if x > y:
                    home_win += p
                elif x == y:
                    draw += p
                else:
                    away_win += p

        total = home_win + draw + away_win
        return Prediction(
            home_win=home_win / total,
            draw=draw / total,
            away_win=away_win / total,
            lambda_home=lh,
            lambda_away=la,
        )


def load_matches_from_db(conn) -> list[dict[str, Any]]:
    """
    Load completed WC fixtures with scores from football.db.
    Only includes fixtures where both teams are registered (openfootball/fifa_fdcp sources).
    football_data rows (NULL team IDs) are excluded by design — they cover domestic leagues.
    Returns one row per fixture_id (first source encountered for duplicates).
    """
    rows = conn.execute(
        """SELECT DISTINCT
               f.id,
               ht.name AS home_team,
               at.name AS away_team,
               ms.home_score,
               ms.away_score
           FROM match_stats ms
           JOIN fixtures f ON ms.fixture_id = f.id
           JOIN teams ht ON f.home_team_id = ht.id
           JOIN teams at ON f.away_team_id = at.id
           WHERE ms.home_score IS NOT NULL
             AND ms.away_score IS NOT NULL
             AND f.status = 'completed'
             AND f.tournament LIKE 'WC%'
        """
    ).fetchall()

    seen: dict[str, dict] = {}
    for row in rows:
        fid = row[0]
        if fid not in seen:
            seen[fid] = {
                "home_team": row[1],
                "away_team": row[2],
                "home_score": row[3],
                "away_score": row[4],
            }
    return list(seen.values())
