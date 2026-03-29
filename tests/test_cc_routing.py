"""Test classify_cc_tier routing logic.

Tier philosophy (2026-03-29):
  C = Qwen local ($0) — knowledge queries, text-only answers (no execution)
  A = Sonnet via claude -p — tasks requiring filesystem/bash execution
  S = Opus — escalation only via plan quality gate, never returned directly

Routing principle: EXECUTE → A (Sonnet) | ANSWER → C (Qwen)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))


def test_knowledge_queries_route_to_qwen():
    """Pure knowledge queries go to Tier C (Qwen local, text-only)."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("qué hace el pipeline DQ?") == "C"
    assert classify_cc_tier("cómo funciona el orchestrator?") == "C"
    assert classify_cc_tier("explica el modelo de tiers") == "C"
    # "describe la arquitectura" → A because "arquitectura" is a planning keyword
    assert classify_cc_tier("describe el módulo de notificaciones") == "C"
    assert classify_cc_tier("cuántas tablas tiene la DB?") == "C"
    assert classify_cc_tier("hola") == "C"
    assert classify_cc_tier("status del sistema") == "C"


def test_execution_tasks_route_to_sonnet():
    """Tasks that need filesystem/bash access go to Tier A (Sonnet)."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("implementa crawler retry con backoff") == "A"
    assert classify_cc_tier("fix el bug en _cc_check") == "A"
    assert classify_cc_tier("crea un test para questionnaire_parser") == "A"
    assert classify_cc_tier("añade endpoint REST para /api/status") == "A"
    assert classify_cc_tier("ejecuta los smoke tests") == "A"
    assert classify_cc_tier("lista archivos en bin/") == "A"
    assert classify_cc_tier("deploy la nueva versión") == "A"
    assert classify_cc_tier("commit los cambios") == "A"
    assert classify_cc_tier("borra los logs viejos") == "A"


def test_refactor_routes_to_sonnet():
    """Refactor needs execution → Tier A."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("refactor diagnostic_writer para usar async") == "A"


def test_planning_routes_to_sonnet():
    """Planning and analysis need Sonnet-level reasoning + execution."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("diseña la arquitectura del nuevo pipeline") == "A"
    assert classify_cc_tier("analiza los cuellos de botella del sistema") == "A"
    assert classify_cc_tier("revisa el código del orchestrator") == "A"
    assert classify_cc_tier("planifica la migración a microservicios") == "A"


def test_long_prompt_routes_to_sonnet():
    """Long prompts imply multi-step tasks → execution needed."""
    from orchestrator import classify_cc_tier

    long_prompt = "Aqui esta el contexto completo: " + "x" * 300
    assert classify_cc_tier(long_prompt) == "A"


def test_exec_keywords_route_to_sonnet():
    """Prompts with execution-context keywords go to Sonnet."""
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("hay un traceback en el log") == "A"
    assert classify_cc_tier("debug el módulo de routing") == "A"
    assert classify_cc_tier("revisa el dockerfile") == "A"


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
    """Only C and A are valid return values (no B, no S)."""
    from orchestrator import classify_cc_tier

    for prompt in ["hola", "implementa X", "diseña plan", ""]:
        tier = classify_cc_tier(prompt)
        assert tier in ("C", "A"), f"Invalid tier {tier} for '{prompt}'"


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
