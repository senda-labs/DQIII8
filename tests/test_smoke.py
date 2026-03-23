"""
tests/test_smoke.py — DQIII8 Pipeline Smoke Tests

Verifica que cada componente del pipeline DQ dispara correctamente.
NO mockear nada — tests contra el sistema real.

Falla → audit score baja a max 80 automáticamente.
Ejecución: python3 -m pytest tests/test_smoke.py -v
"""
import os
import sys
from pathlib import Path

# ── Paths y env ────────────────────────────────────────────────────────────
DQIII8_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

os.environ.setdefault("DQIII8_ROOT", str(DQIII8_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(DQIII8_ROOT / ".env")
except ImportError:
    pass

# ── Imports ────────────────────────────────────────────────────────────────
from domain_classifier import classify_domain
from knowledge_enricher import enrich_with_knowledge
from intent_amplifier import amplify
import openrouter_wrapper
import ollama_wrapper
from db import get_db, query
from embeddings import get_embedding

# ── Prompts canónicos (1 por dominio) ──────────────────────────────────────
CANONICAL: dict[str, str] = {
    "formal_sciences":  "derivative of x squared",
    "natural_sciences": "photosynthesis process",
    "social_sciences":  "inflation monetary policy impact",
    "humanities_arts":  "romanticism in Keats poetry",
    "applied_sciences": "machine learning neural network training",
}


# ── Tests ──────────────────────────────────────────────────────────────────

def test_imports():
    """Todos los módulos core importan sin error."""
    assert callable(classify_domain)
    assert callable(enrich_with_knowledge)
    assert callable(amplify)
    assert openrouter_wrapper is not None
    assert ollama_wrapper is not None
    assert callable(get_db)
    assert callable(get_embedding)


def test_domain_classifier():
    """5 prompts canónicos clasifican al dominio correcto."""
    for expected, prompt in CANONICAL.items():
        domain, confidence, method = classify_domain(prompt)
        assert domain == expected, (
            f"prompt={prompt!r}: esperado={expected!r} obtenido={domain!r} "
            f"(confidence={confidence:.2f}, method={method})"
        )


def test_knowledge_enricher():
    """enrich_with_knowledge devuelve chunks > 0 para cada dominio."""
    for domain, prompt in CANONICAL.items():
        _, chunks = enrich_with_knowledge(prompt, domain)
        assert chunks > 0, (
            f"domain={domain!r}: 0 chunks para prompt={prompt!r}. "
            "¿Ollama corriendo? ¿Index generado?"
        )


def test_intent_amplifier():
    """amplify() devuelve dict con tier (int 1-3), intent, amplified."""
    result = amplify("calculate the derivative of x\u00b2+3x")
    assert isinstance(result, dict), "amplify() debe devolver dict"
    for key in ("tier", "intent", "amplified"):
        assert key in result, f"key {key!r} ausente en {list(result.keys())}"
    assert isinstance(result["tier"], int), (
        f"tier debe ser int, got {type(result['tier'])}"
    )
    assert result["tier"] in (1, 2, 3), f"tier debe ser 1-3, got {result['tier']}"


def test_embeddings():
    """get_embedding devuelve lista de 768 floats (nomic-embed-text)."""
    result = get_embedding("test")
    assert result is not None, "get_embedding devolvió None — ¿Ollama corriendo?"
    assert isinstance(result, list), f"esperado list, got {type(result)}"
    assert len(result) == 768, f"esperado 768 dims, got {len(result)}"


def test_db_connection():
    """La DB es accesible y agent_actions tiene registros."""
    row = query("SELECT COUNT(*) as n FROM agent_actions", fetchone=True)
    count = row["n"]
    assert count > 0, f"agent_actions vacía (count={count})"


def test_knowledge_enricher_get_chunks():
    """get_relevant_chunks returns list[dict] without modifying the prompt."""
    from knowledge_enricher import get_relevant_chunks
    original = "photosynthesis process"
    chunks = get_relevant_chunks(original, "natural_sciences")
    assert isinstance(chunks, list), f"expected list, got {type(chunks)}"
    if chunks:
        assert all(isinstance(c, dict) for c in chunks), "each item must be dict"
        assert all("text" in c and "score" in c for c in chunks), "each dict must have text+score"
    assert original == "photosynthesis process", "prompt must not be mutated"


def test_amplifier_entity_not_context():
    """Entity extracted from original prompt, not from domain-context prefix."""
    result = amplify("calculate WACC for Tesla", domain="social_sciences")
    assert result["entity"] != "CONTEXT", (
        f"entity should not be 'CONTEXT' (double-enrichment bug). Got: {result['entity']!r}"
    )
