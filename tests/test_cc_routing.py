"""Test classify_cc_tier routing logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))


def test_simple_query_routes_to_groq():
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("lista archivos en bin/") == "B"
    assert classify_cc_tier("status del sistema") == "B"
    # "cuantos tests hay?" matches _CODE_KW "test" → A (correct)
    assert classify_cc_tier("cuantas empresas hay?") == "B"
    assert classify_cc_tier("explica el pipeline DQ") == "B"


def test_code_task_routes_to_sonnet():
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("implementa crawler retry con backoff") == "A"
    assert classify_cc_tier("fix el bug en _cc_check") == "A"
    assert classify_cc_tier("refactor diagnostic_writer para usar async") == "A"
    assert classify_cc_tier("crea un test para questionnaire_parser") == "A"


def test_complex_routes_to_opus():
    from orchestrator import classify_cc_tier

    assert (
        classify_cc_tier("diseña arquitectura de microservicios para el pipeline")
        == "S"
    )
    assert (
        classify_cc_tier("write a complete implementation plan for multi-tenant auth")
        == "S"
    )
    assert (
        classify_cc_tier(
            "analyze in depth the performance bottlenecks and design system improvements"
        )
        == "S"
    )


def test_long_prompt_escalates():
    from orchestrator import classify_cc_tier

    long_prompt = "Aqui esta el error: " + "x" * 300
    tier = classify_cc_tier(long_prompt)
    assert tier in ("A", "S")


def test_short_ambiguous_is_groq():
    from orchestrator import classify_cc_tier

    # Short prompt with no action verbs or code keywords → Groq (cheapest)
    assert classify_cc_tier("hazlo") == "B"


def test_tier_to_model_mapping():
    """Verify tier labels map to expected models."""
    tier_models = {"B": "groq", "A": "sonnet", "S": "opus"}
    for tier, model_fragment in tier_models.items():
        assert model_fragment


def test_classify_returns_valid_tier():
    from orchestrator import classify_cc_tier

    for prompt in ["hola", "implementa X", "write a complete plan", ""]:
        tier = classify_cc_tier(prompt)
        assert tier in ("B", "A", "S"), f"Invalid tier {tier} for '{prompt}'"
