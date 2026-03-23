"""
JAL Scoring Engine v3
=====================
Multi-Criteria Decision Analysis (MCDA) with Shannon Entropy.

Terminology applied correctly:
- Shannon Entropy H: measures disorder in the failure distribution.
  High entropy = failures spread across many categories = unstable
  system, hard to diagnose.
  Low entropy = failures concentrated in one category = specific
  problem, easier to fix.

- Superposition (classical): a step is in an indeterminate state
  [0.0, 1.0] until Gemini evaluates it. Not binary.

- Failure entanglement: measured correlation between error categories.
  A 'dependency' failure has propagation=0.8 because it statistically
  drags other steps along.

- Historical density function: empirical success distribution of
  Claude Code by task type, built with each execution.
  Enables calculating prior probability before executing.

The score is NOT an opinion. It is a reproducible equation.
"""

import math
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
sys.path.insert(0, str(JARVIS / "bin"))
from db import get_db

# ── Base propagation per category (empirical, updatable) ──
CATEGORY_PROPAGATION = {
    "dependency":  0.80,  # external failure drags everything
    "permission":  0.90,  # total system blockage
    "config":      0.60,  # affects multiple steps
    "env":         0.70,  # missing variable = everything using it fails
    "logic":       0.30,  # internal error, generally isolated
    "timeout":     0.20,  # rarely propagates
    "unknown":     0.40,  # maximum uncertainty assigned as average
}

PASS_THRESHOLD  = 0.85   # Ψ minimum to pass
BLOCKER_CEILING = 0.60   # ceiling if a critical step is blocked
ENTROPY_WEIGHT  = 0.15   # maximum penalty for entropy
MOMENTUM_CAP    = 0.03   # maximum bonus for improvement between attempts


@dataclass
class StepMeasurement:
    """
    Measurement of a step after execution.
    Indeterminate state until completion_pct is assigned by Gemini.
    """
    step_number:    int
    description:    str
    weight:         float        # importancia [0.0, 1.0]
    criticality:    int          # exponente [1, 2, 3]
    completion:     float        # proportion completed [0.0, 1.0]
    error_category: str = "unknown"
    error_message:  str = ""

    @property
    def score(self) -> float:
        """
        score_i = completion^criticality × weight
        Exponentiation penalizes failures in critical steps
        non-linearly: a critical(3) step at 50%
        contributes 0.5^3 = 0.125, not 0.5.
        """
        return (self.completion ** self.criticality) * self.weight

    @property
    def is_blocker(self) -> bool:
        """Critical step below 50% blocks the objective."""
        return self.criticality == 3 and self.completion < 0.50

    @property
    def severity(self) -> int:
        """Severity derived from criticality and completion."""
        if self.completion >= 1.0:
            return 0
        base = self.criticality
        if self.completion == 0.0:
            base += 2
        elif self.completion < 0.3:
            base += 1
        return min(base, 5)


@dataclass
class ScoringResult:
    """Complete result of an evaluation."""
    objective_id:    str
    attempt:         int
    steps:           list[StepMeasurement]
    prev_score:      float = 0.0

    # Calculados en compute()
    score_raw:       float = 0.0
    entropy_H:       float = 0.0
    entropy_penalty: float = 0.0
    blocker_penalty: float = 0.0
    momentum_bonus:  float = 0.0
    score_final:     float = 0.0
    delta_score:     float = 0.0
    convergence_est: Optional[float] = None
    converges:       bool = False
    errors:          list[dict] = field(default_factory=list)

    def compute(self) -> "ScoringResult":
        self._normalize_weights()
        self.score_raw      = self._calc_score_raw()
        self.entropy_H      = self._calc_entropy()
        self.entropy_penalty = self.score_raw * (1 - ENTROPY_WEIGHT * self.entropy_H)
        self.blocker_penalty = (
            min(self.entropy_penalty, BLOCKER_CEILING)
            if any(s.is_blocker for s in self.steps)
            else self.entropy_penalty
        )
        self.delta_score   = self.blocker_penalty - self.prev_score
        self.momentum_bonus = (
            min(MOMENTUM_CAP, self.delta_score * 0.5)
            if self.attempt > 1 and self.delta_score > 0
            else 0.0
        )
        self.score_final   = round(
            min(1.0, self.blocker_penalty + self.momentum_bonus), 4
        )
        self.delta_score   = round(self.score_final - self.prev_score, 4)
        self.converges, self.convergence_est = self._calc_convergence()
        self.errors        = self._classify_errors()
        return self

    def _normalize_weights(self):
        total = sum(s.weight for s in self.steps)
        if total > 0 and abs(total - 1.0) > 0.001:
            for s in self.steps:
                s.weight /= total

    def _calc_score_raw(self) -> float:
        total_w = sum(s.weight for s in self.steps)
        if total_w == 0:
            return 0.0
        return sum(s.score for s in self.steps) / total_w

    def _calc_entropy(self) -> float:
        """
        Shannon Entropy over the failure category distribution.

        H = -Σ p_i × log2(p_i)

        p_i = proportion of failed steps in category i.
        Normalized by log2(N_categories) → range [0, 1].

        H=0: all failures are in the same category
             → specific problem, solvable.
        H=1: failures uniformly distributed across all categories
             → unstable system, hard to diagnose.
        """
        failed = [s for s in self.steps if s.completion < 0.5]
        if not failed:
            return 0.0

        counts: dict[str, int] = {}
        for s in failed:
            counts[s.error_category] = counts.get(s.error_category, 0) + 1

        total = len(failed)
        H = -sum(
            (c / total) * math.log2(c / total)
            for c in counts.values() if c > 0
        )
        # Normalize by log2(observed_categories), not by the total possible.
        # This way H=1.0 when failures are uniformly spread across
        # all categories that actually appear (maximum disorder).
        n_cats = len(counts)
        max_H  = math.log2(n_cats) if n_cats > 1 else 1.0
        return H / max_H if max_H > 0 else 0.0

    def _calc_convergence(self) -> tuple[bool, Optional[float]]:
        """
        Estimates whether the system converges to PASS_THRESHOLD and in how many attempts.
        Uses the current delta as a linear progress estimator.
        """
        if self.score_final >= PASS_THRESHOLD:
            return True, 0.0
        if self.delta_score <= 0:
            return False, None  # Does not converge with current strategy
        remaining = PASS_THRESHOLD - self.score_final
        return True, round(remaining / self.delta_score, 1)

    def _classify_errors(self) -> list[dict]:
        """
        Classifies errors by mathematical criticality.
        critical_score = (severity × propagation × fix_complexity) / 25
        Range [0, 1]: 1.0 = fatal error that blocks everything and is hard to fix.
        """
        errors = []
        for i, s in enumerate(self.steps):
            if s.completion >= 1.0 or not s.error_message:
                continue
            prop = CATEGORY_PROPAGATION.get(
                s.error_category, CATEGORY_PROPAGATION["unknown"]
            )
            prop_adj    = prop * (s.criticality / 3)
            fix_complex = max(1, s.criticality)
            sev         = s.severity
            cscore      = round((sev * prop_adj * fix_complex) / 25.0, 4)

            errors.append({
                "error_code":     f"E{i+1:03d}",
                "step":           s.step_number,
                "category":       s.error_category,
                "severity":       sev,
                "propagation":    round(prop_adj, 3),
                "fix_complexity": fix_complex,
                "critical_score": cscore,
                "label": (
                    "BLOCKER"  if cscore >= 0.60 else
                    "CRITICAL" if cscore >= 0.30 else
                    "MODERATE" if cscore >= 0.10 else
                    "MINOR"
                ),
                "message": s.error_message[:300],
            })
        return sorted(errors, key=lambda e: e["critical_score"], reverse=True)

    def to_dict(self) -> dict:
        return {
            "objective_id":   self.objective_id,
            "attempt":        self.attempt,
            "score_raw":      round(self.score_raw, 4),
            "entropy_H":      round(self.entropy_H, 4),
            "entropy_penalty":round(self.entropy_penalty, 4),
            "blocker_penalty":round(self.blocker_penalty, 4),
            "momentum_bonus": round(self.momentum_bonus, 4),
            "score_final":    self.score_final,
            "delta_score":    self.delta_score,
            "converges":      self.converges,
            "convergence_est":self.convergence_est,
            "has_blocker":    any(s.is_blocker for s in self.steps),
            "steps_total":    len(self.steps),
            "steps_completed":sum(1 for s in self.steps if s.completion >= 0.85),
            "steps_failed":   sum(1 for s in self.steps if s.completion < 0.50),
            "errors":         self.errors,
            "steps": [
                {
                    "n":           s.step_number,
                    "desc":        s.description[:80],
                    "weight":      round(s.weight, 3),
                    "criticality": s.criticality,
                    "completion":  round(s.completion, 3),
                    "score":       round(s.score, 4),
                    "is_blocker":  s.is_blocker,
                    "category":    s.error_category,
                }
                for s in self.steps
            ]
        }

    def save(self):
        """Persists immutable snapshot to DB."""
        d = self.to_dict()
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO jal_scoring_snapshots
                (objective_id, attempt, score_raw, entropy_H,
                 entropy_penalty, blocker_penalty, momentum_bonus,
                 score_final, delta_score, convergence_est, converges,
                 steps_total, steps_completed, steps_failed, has_blocker,
                 breakdown_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                d["objective_id"], d["attempt"],
                d["score_raw"], d["entropy_H"],
                d["entropy_penalty"], d["blocker_penalty"],
                d["momentum_bonus"], d["score_final"],
                d["delta_score"], d["convergence_est"],
                1 if d["converges"] else 0,
                d["steps_total"], d["steps_completed"],
                d["steps_failed"], 1 if d["has_blocker"] else 0,
                json.dumps(d)
            ))


def load_from_db(objective_id: str, attempt: int) -> ScoringResult:
    """Loads step state from DB and builds ScoringResult."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT step_number, description, weight, criticality,
                   completion_pct, error_category, result_summary
            FROM jal_steps
            WHERE objective_id=? AND attempt=?
            ORDER BY step_number
        """, (objective_id, attempt)).fetchall()

        prev = conn.execute("""
            SELECT score_final FROM jal_scoring_snapshots
            WHERE objective_id=? AND attempt<?
            ORDER BY attempt DESC LIMIT 1
        """, (objective_id, attempt)).fetchone()

    steps = [
        StepMeasurement(
            step_number    = r[0],
            description    = r[1],
            weight         = r[2] or 0.33,
            criticality    = r[3] or 1,
            completion     = r[4] or 0.0,
            error_category = r[5] or "unknown",
            error_message  = r[6] or "",
        )
        for r in rows
    ]
    return ScoringResult(
        objective_id = objective_id,
        attempt      = attempt,
        steps        = steps,
        prev_score   = prev[0] if prev else 0.0,
    ).compute()
