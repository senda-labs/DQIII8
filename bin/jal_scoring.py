"""
JAL Scoring Engine v3
=====================
Multi-Criteria Decision Analysis (MCDA) con Shannon Entropy.

Terminología aplicada correctamente:
- Shannon Entropy H: mide el desorden en la distribución de fallos.
  Alta entropía = fallos dispersos en muchas categorías = sistema
  inestable, difícil de diagnosticar.
  Baja entropía = fallos concentrados en una categoría = problema
  específico, más fácil de corregir.

- Superposición (clásica): un paso está en estado indeterminado
  [0.0, 1.0] hasta que Gemini lo evalúa. No es binario.

- Entrelazamiento de fallos: correlación medida entre categorías
  de error. Un fallo de tipo 'dependency' tiene propagation=0.8
  porque estadísticamente arrastra otros pasos.

- Función de densidad histórica: distribución empírica de éxito
  de Claude Code por tipo de tarea, construida con cada ejecución.
  Permite calcular prior probability antes de ejecutar.

El score NO es una opinión. Es una ecuación reproducible.
"""

import math
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

DB = Path("/root/jarvis/database/jarvis_metrics.db")

# ── Propagación base por categoría (empírica, actualizable) ──
CATEGORY_PROPAGATION = {
    "dependency":  0.80,  # fallo externo arrastra todo
    "permission":  0.90,  # bloqueo total del sistema
    "config":      0.60,  # afecta múltiples pasos
    "env":         0.70,  # variable faltante = falla todo lo que la usa
    "logic":       0.30,  # error interno, generalmente aislado
    "timeout":     0.20,  # raramente se propaga
    "unknown":     0.40,  # incertidumbre máxima asignada como media
}

PASS_THRESHOLD  = 0.85   # Ψ mínimo para aprobar
BLOCKER_CEILING = 0.60   # techo si hay paso crítico bloqueado
ENTROPY_WEIGHT  = 0.15   # penalización máxima por entropía
MOMENTUM_CAP    = 0.03   # bonus máximo por mejora entre intentos


@dataclass
class StepMeasurement:
    """
    Medición de un paso tras ejecución.
    Estado indeterminado hasta que completion_pct es asignado por Gemini.
    """
    step_number:    int
    description:    str
    weight:         float        # importancia [0.0, 1.0]
    criticality:    int          # exponente [1, 2, 3]
    completion:     float        # proporción completada [0.0, 1.0]
    error_category: str = "unknown"
    error_message:  str = ""

    @property
    def score(self) -> float:
        """
        score_i = completion^criticality × weight
        La exponenciación penaliza fallos en pasos críticos
        de forma no lineal: un paso crítico(3) al 50%
        contribuye 0.5^3 = 0.125, no 0.5.
        """
        return (self.completion ** self.criticality) * self.weight

    @property
    def is_blocker(self) -> bool:
        """Paso crítico con menos del 50% bloquea el objetivo."""
        return self.criticality == 3 and self.completion < 0.50

    @property
    def severity(self) -> int:
        """Severidad derivada de criticality y completion."""
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
    """Resultado completo de una evaluación."""
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
        Shannon Entropy sobre distribución de categorías de fallo.

        H = -Σ p_i × log2(p_i)

        p_i = proporción de pasos fallidos en categoría i.
        Normalizado por log2(N_categorías) → rango [0, 1].

        H=0: todos los fallos son de la misma categoría
             → problema específico, solucionable.
        H=1: fallos uniformemente distribuidos en todas las categorías
             → sistema inestable, diagnóstico difícil.
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
        # Normalizar por log2(categorias_observadas), no por el total posible.
        # Así H=1.0 cuando los fallos están uniformemente dispersos entre
        # todas las categorías que realmente aparecen (máximo desorden).
        n_cats = len(counts)
        max_H  = math.log2(n_cats) if n_cats > 1 else 1.0
        return H / max_H if max_H > 0 else 0.0

    def _calc_convergence(self) -> tuple[bool, Optional[float]]:
        """
        Estima si el sistema converge a PASS_THRESHOLD y en cuántos intentos.
        Usa el delta actual como estimador lineal de progreso.
        """
        if self.score_final >= PASS_THRESHOLD:
            return True, 0.0
        if self.delta_score <= 0:
            return False, None  # No converge con estrategia actual
        remaining = PASS_THRESHOLD - self.score_final
        return True, round(remaining / self.delta_score, 1)

    def _classify_errors(self) -> list[dict]:
        """
        Clasifica errores por criticidad matemática.
        critical_score = (severity × propagation × fix_complexity) / 25
        Rango [0, 1]: 1.0 = error fatal que bloquea todo y es difícil de arreglar.
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
                    "BLOQUEANTE" if cscore >= 0.60 else
                    "CRITICO"    if cscore >= 0.30 else
                    "MODERADO"   if cscore >= 0.10 else
                    "MENOR"
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
        """Persiste snapshot inmutable en BD."""
        d = self.to_dict()
        conn = sqlite3.connect(DB)
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
        conn.commit()
        conn.close()


def load_from_db(objective_id: str, attempt: int) -> ScoringResult:
    """Carga el estado de pasos desde BD y construye ScoringResult."""
    conn = sqlite3.connect(DB)
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
    conn.close()

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
