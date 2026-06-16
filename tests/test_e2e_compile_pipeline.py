"""E2E: domain_classifier → confidence_gate → plan_compiler → verifiable output.

No network, no LLM calls — exercises the deterministic pipeline spine.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin" / "agents"))
sys.path.insert(0, str(ROOT / "bin" / "core"))

PROMPT = ("analiza los errores del invoice extractor de abril y planifica "
          "la remediacion con tests de regresion")


def test_pipeline_spine():
    # 1. Domain classification (centroid scorer; tolerate no-embedding env)
    try:
        from domain_classifier import classify_domain
        domain = classify_domain(PROMPT)
        assert domain  # non-empty
    except Exception:
        domain = "applied_sciences"  # offline fallback — spine continues

    # 2. Confidence gate — Tier A with weak chunks must block (benchmark rule)
    from confidence_gate import should_enrich
    weak = [{"text": "generic definition of invoices", "score": 0.31}]
    assert should_enrich(PROMPT, domain, weak, tier=3) is False
    assert should_enrich(PROMPT, domain, [], tier=3) is False
    assert should_enrich(PROMPT, domain, weak, tier=1) is True  # Tier C always

    # 3. Compile
    from plan_compiler import dq_compile
    plan = dq_compile(PROMPT)
    assert plan.intent_pattern in {"analyze", "plan", "debug", "test"}

    # 4. Verifiable output contract
    out = plan.render()
    assert out.startswith("[EXECUTION PLAN")
    assert out.count("exit:") == len(plan.plan_fases)
    assert "AUDIT CHECKLIST" in out and "INVARIANTES" in out


def test_amplifier_tier_a_carries_plan():
    import intent_amplifier as ia
    amplified, n = ia._build_amplified_prompt(
        PROMPT,
        {"action": "analyze", "entity": "invoice", "niche": "", "tokens": PROMPT.split()},
        {"id": "analyze", "score": 2, "tier": 3},
        [{"domain": "applied_sciences", "score": 0.9}], [], None, tier=3,
    )
    assert "[EXECUTION PLAN" in amplified


def test_confidence_gate_tier_b_blocks_generic_passes_specific():
    """Rule 4 pinned: Tier B blocks definitional chunks, passes chunks with
    >=3 specificity indicators (digits + year + %; has_specific_data contract)."""
    from confidence_gate import should_enrich
    generic = [{"text": "invoices are defined as documents", "score": 0.50}]
    assert should_enrich(PROMPT, "applied_sciences", generic, tier=2) is False

    # 2 indicators (digits + year) is NOT enough — threshold is 3, by design
    two_ind = [{"text": "In April 2026 the extractor failed 37 times", "score": 0.85}]
    assert should_enrich(PROMPT, "applied_sciences", two_ind, tier=2) is False

    three_ind = [{"text": "Q1 2026: extractor error rate 8.3% across 422 runs", "score": 0.85}]
    assert should_enrich(PROMPT, "applied_sciences", three_ind, tier=2) is True


def test_plan_render_is_idempotent_across_calls():
    from plan_compiler import dq_compile
    r1 = dq_compile(PROMPT).render()
    r2 = dq_compile(PROMPT).render()
    assert r1 == r2
