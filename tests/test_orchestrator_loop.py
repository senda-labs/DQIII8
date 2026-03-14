"""Tests del OrchestratorLoop — sin llamadas reales a Claude ni BD."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bin.orchestrator_loop import OrchestratorLoop

loop = OrchestratorLoop()


def test_capture_with_final_report():
    """capture() extrae correctamente el FINAL_REPORT embebido."""
    output = """
    Hice algunas cosas.
    ---FINAL_REPORT---
    {"success": true, "files_modified": ["a.py"],
     "errors_found": [], "fixes_applied": ["fix x"],
     "lessons": ["[test] causa → fix"], "blocker": null,
     "next_step": "continuar"}
    ---END_REPORT---
    """
    result = loop.capture(output)
    assert result["success"] is True
    assert "a.py" in result["files_modified"]
    assert result["blocker"] is None
    assert result["lessons"] == ["[test] causa → fix"]


def test_capture_fallback_on_error():
    """capture() infiere success=False si hay palabras de error en el output."""
    output = "Traceback (most recent call last): Error en línea 42"
    result = loop.capture(output)
    assert result["success"] is False


def test_capture_fallback_no_error():
    """capture() infiere success=True cuando hay más señales de éxito que de error."""
    output = "File created successfully. All steps completed and done."
    result = loop.capture(output)
    assert result["success"] is True


def test_capture_fallback_no_signals():
    """capture() devuelve success=False cuando no hay señales reconocibles (ni éxito ni error)."""
    output = "Todo fue bien. Archivos modificados. Completado."
    result = loop.capture(output)
    assert result["success"] is False
    assert result.get("inferred") is True


def test_build_prompt_contains_final_report_marker():
    """build_prompt() incluye los marcadores FINAL_REPORT necesarios."""
    context = {"project": "test", "project_state": "estado", "lessons": []}
    objective = {
        "objective": "Test objetivo",
        "success_criteria": "OK",
        "priority": "high",
    }
    prompt = loop.build_prompt(objective, context)
    assert "---FINAL_REPORT---" in prompt
    assert "---END_REPORT---" in prompt
    assert "success" in prompt


def test_build_prompt_includes_objective():
    """build_prompt() incluye el texto del objetivo y los criterios."""
    context = {"project": "myproject", "project_state": "", "lessons": []}
    objective = {
        "objective": "Implementar autenticación JWT",
        "success_criteria": "Tests pasan al 100%",
        "priority": "high",
    }
    prompt = loop.build_prompt(objective, context)
    assert "Implementar autenticación JWT" in prompt
    assert "Tests pasan al 100%" in prompt
    assert "myproject" in prompt


def test_capture_returns_required_keys():
    """capture() siempre devuelve las 7 claves requeridas."""
    required = {
        "success",
        "files_modified",
        "errors_found",
        "fixes_applied",
        "lessons",
        "blocker",
        "next_step",
    }
    # Con FINAL_REPORT
    with_report = loop.capture(
        '---FINAL_REPORT---\n{"success":true,"files_modified":[],'
        '"errors_found":[],"fixes_applied":[],"lessons":[],'
        '"blocker":null,"next_step":"ok"}\n---END_REPORT---'
    )
    assert required.issubset(with_report.keys())

    # Fallback
    fallback = loop.capture("sin errores")
    assert required.issubset(fallback.keys())


def test_analyze_returns_required_keys():
    """analyze() devuelve siempre project, timestamp y pending_objectives."""
    ctx = loop.analyze("nonexistent-project-xyz")
    assert "project" in ctx
    assert "timestamp" in ctx
    assert "pending_objectives" in ctx
    assert ctx["project"] == "nonexistent-project-xyz"
    assert isinstance(ctx["pending_objectives"], list)
