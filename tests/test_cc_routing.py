"""Test classify_cc_tier routing logic.

Tier philosophy:
  C = Ollama qwen2.5-coder (code execution workhorse, $0 local)
  B = Groq llama-3.3-70b (simple queries, $0 cloud)
  A = Sonnet (planning, analysis, supervision)
  S = Opus (escalation only — never returned by classify_cc_tier)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))


def test_simple_query_routes_to_groq():
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("lista archivos en bin/") == "B"
    assert classify_cc_tier("status del sistema") == "B"
    assert classify_cc_tier("cuantas empresas hay?") == "B"
    assert classify_cc_tier("explica el pipeline DQ") == "B"
    assert classify_cc_tier("hazlo") == "B"


def test_code_task_routes_to_ollama():
    """Code tasks go to Tier C (local Ollama), not Sonnet."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("implementa crawler retry con backoff") == "C"
    assert classify_cc_tier("fix el bug en _cc_check") == "C"
    assert classify_cc_tier("crea un test para questionnaire_parser") == "C"
    assert classify_cc_tier("añade endpoint REST para /api/status") == "C"


def test_refactor_routes_to_ollama():
    """Refactor is code work → Tier C."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("refactor diagnostic_writer para usar async") == "C"


def test_planning_routes_to_sonnet():
    """Planning and analysis need Sonnet-level reasoning."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("diseña la arquitectura del nuevo pipeline") == "A"
    assert classify_cc_tier("analiza los cuellos de botella del sistema") == "A"
    assert classify_cc_tier("revisa el código del orchestrator") == "A"
    assert classify_cc_tier("planifica la migración a microservicios") == "A"


def test_long_prompt_routes_to_sonnet():
    from orchestrator import classify_cc_tier

    long_prompt = "Aqui esta el contexto completo: " + "x" * 300
    assert classify_cc_tier(long_prompt) == "A"


def test_opus_never_returned_directly():
    """classify_cc_tier NEVER returns S. Opus is escalation only."""
    from orchestrator import classify_cc_tier

    prompts = [
        "hola",
        "implementa X",
        "diseña arquitectura completa",
        "write a complete implementation plan",
        "analyze in depth everything",
        "",
    ]
    for p in prompts:
        tier = classify_cc_tier(p)
        assert tier != "S", f"Got S for '{p}' — Opus must be escalation only"


def test_classify_returns_valid_tier():
    from orchestrator import classify_cc_tier

    for prompt in ["hola", "implementa X", "diseña plan", ""]:
        tier = classify_cc_tier(prompt)
        assert tier in ("C", "B", "A"), f"Invalid tier {tier} for '{prompt}'"


def test_escalation_logic():
    """should_escalate_to_opus triggers on poor Sonnet output."""
    from orchestrator import should_escalate_to_opus

    # Failed execution → escalate
    assert should_escalate_to_opus("big task", "", False) is True

    # Too short output for a long prompt → escalate
    assert should_escalate_to_opus("long " * 30, "ok", True) is True

    # Sonnet admits failure → escalate
    assert should_escalate_to_opus("task", "I can't do this", True) is True
    assert should_escalate_to_opus("task", "no puedo completar", True) is True

    # Good output → don't escalate
    assert should_escalate_to_opus("task", "x" * 300, True) is False
