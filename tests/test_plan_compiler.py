"""tests/test_plan_compiler.py — Execution Plan Compiler contract + templates."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin" / "agents"))

from plan_compiler import (  # noqa: E402
    AMPLIFIER_INTENT_MAP,
    PATTERNS,
    ExecutionPlan,
    PhaseSpec,
    _SHARED_INVARIANTS,
    _T,
    _infer_pattern,
    dq_compile,
)


def test_contract_returns_execution_plan():
    plan = dq_compile("debug the crash in invoice_extractor when PDF is empty")
    assert isinstance(plan, ExecutionPlan)
    assert plan.intent_pattern == "debug"
    assert len(plan.plan_fases) >= 3
    assert all(isinstance(p, PhaseSpec) for p in plan.plan_fases)
    assert plan.pseudocodigo.strip()
    assert len(plan.audit_checklist) >= 3
    assert len(plan.validation_tests) >= 2
    assert len(plan.invariantes_flujo) >= 3
    rendered = plan.render()
    assert "[EXECUTION PLAN" in rendered
    assert "AUDIT CHECKLIST" in rendered


_PROBES = {  # one representative prompt per pattern
    "plan": "planifica la arquitectura del nuevo servicio",
    "debug": "fix the crash when input is empty",
    "analyze": "analiza el rendimiento del tier B en abril",
    "generate": "genera un script de backup incremental",
    "report": "prepara el informe ejecutivo trimestral",
    "refactor": "refactor the database layer into modules",
    "research": "investiga el estado del arte en rerankers",
    "test": "escribe tests con cobertura para el parser",
    "deploy": "deploy the health check to production",
    "review": "haz code review del ultimo commit",
    "optimize": "optimiza el query que tarda 10 segundos",
    "explain": "explica que es un circuit breaker",
    "migrate": "migra los datos de MySQL a Postgres",
    "integrate": "integra la API de Telegram con webhook",
}


@pytest.mark.parametrize("pattern", sorted(_T.keys()))
def test_each_pattern_compiles_and_renders(pattern):
    plan = dq_compile(_PROBES[pattern], intent_pattern=pattern)
    assert plan.intent_pattern == pattern
    assert 3 <= len(plan.plan_fases) <= 6
    # Wave semantics: every depends_on names an earlier phase (DAG, no cycles)
    seen = set()
    for ph in plan.plan_fases:
        assert all(d in seen for d in ph.depends_on), f"{pattern}:{ph.name} forward dep"
        seen.add(ph.name)
    r = plan.render()
    for marker in ("FASES", "PSEUDOCÓDIGO", "AUDIT CHECKLIST", "VALIDATION TESTS", "INVARIANTES"):
        assert marker in r, f"{pattern} render missing {marker}"
    assert "{entity}" not in r  # parametrization applied


@pytest.mark.parametrize("pattern", sorted(_PROBES.keys()))
def test_inference_hits_expected_pattern(pattern):
    inferred, conf = _infer_pattern(_PROBES[pattern])
    assert inferred == pattern, f"probe for {pattern} inferred as {inferred}"
    assert conf > 0


def test_shared_invariants_present_in_all():
    for pattern in _T:
        plan = dq_compile("x " + _PROBES[pattern], intent_pattern=pattern)
        for inv in _SHARED_INVARIANTS:
            assert inv in plan.invariantes_flujo


def test_empty_prompt_raises():
    with pytest.raises(ValueError):
        dq_compile("   ")


def test_unknown_forced_pattern_raises():
    with pytest.raises(ValueError):
        dq_compile("hola", intent_pattern="conquer")


def test_amplifier_intent_map_total():
    amplifier_ids = {"analyze", "generate", "optimize", "debug", "research",
                     "summarize", "compare", "forecast", "explain", "transform",
                     "validate", "plan", "automate", "report"}
    assert set(AMPLIFIER_INTENT_MAP) == amplifier_ids
    assert set(AMPLIFIER_INTENT_MAP.values()) <= set(_T)


def test_no_keyword_prompt_falls_back_to_explain():
    plan = dq_compile("qwzx 12345 lorem")
    assert plan.intent_pattern == "explain"
    assert plan.confidence == 0.0


# ── v1.1 regression tests (review 2026-06-10) ────────────────────────────────

from plan_compiler import _detect_entity  # noqa: E402


def test_entity_is_never_the_leading_imperative_verb():
    """v1.0 bug: 'Analiza el rendimiento…' yielded entity='Analiza' and tier-3
    prompts carried nonsense like 'the question Analiza must answer'."""
    assert _detect_entity("Analiza el rendimiento del pipeline") == "the target"
    assert _detect_entity("Corrige el error en el script") == "the target"
    assert _detect_entity("Escribe un test para la funcion") == "the target"
    assert _detect_entity("Can you fix the bot") == "the target"
    # Real entities still detected after the verb is skipped
    assert _detect_entity("Planifica la migracion del bot de Telegram") == "Telegram"
    assert _detect_entity("debug the crash in invoice_extractor") == "invoice_extractor"


def test_inference_handles_spanish_accents():
    """v1.0 bug: 'qué es' failed to match keyword 'que es' (no diacritic folding),
    so the prompt fell through to 'integrate' via the 'webhook' keyword."""
    pattern, conf = _infer_pattern("qué es un webhook")
    assert pattern == "explain"
    assert conf > 0
    pattern, _ = _infer_pattern("Diseña la migración a Postgres")
    assert pattern in ("plan", "migrate")  # 'diseña' and 'migra…' both legitimate


def test_single_keyword_hit_confidence_is_below_hook_threshold():
    """Pins the hook gating contract: 1 hit → 0.333 < 0.34 (hook skips);
    2 hits → 0.667 ≥ 0.34 (hook injects)."""
    _, conf1 = _infer_pattern("analiza esto")
    assert conf1 == 0.333
    plan = dq_compile("fix the bug")  # debug: 'fix' + 'bug' = 2 hits
    assert plan.confidence >= 0.34


def test_idempotent_compile():
    a = dq_compile(_PROBES["debug"]).render()
    b = dq_compile(_PROBES["debug"]).render()
    assert a == b  # fingerprint invariant: same input → same plan


def test_tier_a_prompt_carries_execution_plan():
    """Verify tier-3 prompt builder appends execution plan block.

    Uses _build_amplified_prompt directly to avoid embedding-backend dependency
    (Ollama/bge-m3 not available in test env — same issue noted by Opus in A1).
    """
    import intent_amplifier as ia
    amplified, _ = ia._build_amplified_prompt(
        "planifica la migracion del bot de Telegram a webhooks",
        {"action": "plan", "entity": "Telegram", "niche": "", "tokens": []},
        {"id": "plan", "score": 2, "tier": 3},
        [{"domain": "applied_sciences", "score": 0.9}], [], None, tier=3,
    )
    assert "[EXECUTION PLAN" in amplified
