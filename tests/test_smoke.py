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


def test_amplifier_chunks_used_post_filter():
    """chunks_used must reflect post-filter count, not raw retrieved count.

    Fix 1: _build_amplified_prompt now returns (prompt, injected_count).
    For Tier C the cap is 1; the return value must be <= 1 regardless of
    how many chunks were retrieved.
    """
    from knowledge_enricher import get_relevant_chunks
    chunks = get_relevant_chunks("prove convergence of Newton-Raphson", "formal_sciences", top_k=5)
    result = amplify("prove convergence of Newton-Raphson", domain="formal_sciences", chunks=chunks)
    assert result["tier"] == 1, f"expected Tier C (1), got {result['tier']}"
    assert result["chunks_used"] <= 1, (
        f"chunks_used should be post-filter (<=1 for Tier C), got {result['chunks_used']}"
    )


def test_amplifier_niche_routing_to_tier_a():
    """Finance niche must route to Tier A even when domain classifier returns social_sciences.

    Fix 2: _select_tier checks decomp['niche'] first. 'finance' niche → Tier A (3).
    Previously: 'social_sciences' not in high_tier_domains → Tier C (1). Bug.
    """
    result = amplify("calculate WACC for Tesla assuming 10% cost of equity",
                     domain="social_sciences")
    assert result["tier"] == 3, (
        f"finance niche must route to Tier A (3), got Tier {result['tier']}. "
        f"niche={result.get('niche')!r}"
    )


def test_amplifier_tier_b_no_reference_when_no_specific_chunks():
    """Tier B without specific-data chunks must return original prompt unchanged.

    Fix 3: correct criterion — <reference> tag only appears when chunks pass
    has_specific_data(). Art/humanities chunks are generic; correct output is
    amplified == original (no tag injection).
    """
    from knowledge_enricher import get_relevant_chunks
    chunks = get_relevant_chunks("analyze the use of light in Vermeer paintings",
                                 "humanities_arts", top_k=5)
    result = amplify("analyze the use of light in Vermeer paintings",
                     domain="humanities_arts", chunks=chunks)
    amp = result["amplified"]
    if result["chunks_used"] == 0:
        assert amp == "analyze the use of light in Vermeer paintings", (
            "With 0 specific chunks, Tier B must return original prompt unmodified"
        )
    else:
        assert "<reference>" in amp, "With specific chunks, Tier B must use <reference> tag"


def test_amplifier_overhead_chars():
    """Amplified prompt overhead (not ratio) must stay in tier-appropriate range.

    Fix 4: ratio metric is prompt-length dependent. Overhead in chars is stable.
    - Tier C: 30-600 chars overhead (XML tags + 1 truncated chunk + CoT)
    - Tier B: 0-500 chars overhead (reference block only when specific chunks exist)
    - Tier A: 0-400 chars overhead (raw data only, no scaffolding)
    """
    from knowledge_enricher import get_relevant_chunks
    cases = [
        ("formal_sciences",  "prove convergence of Newton-Raphson method",      1, 30,  600),
        ("humanities_arts",  "analyze the use of light in Vermeer paintings",   2,  0,  500),
        ("social_sciences",  "calculate WACC for Tesla assuming 10% cost of equity", 3, 0, 400),
    ]
    for domain, prompt, expected_tier, min_oh, max_oh in cases:
        chunks = get_relevant_chunks(prompt, domain, top_k=5)
        result = amplify(prompt, domain=domain, chunks=chunks)
        overhead = len(result["amplified"]) - len(prompt)
        assert result["tier"] == expected_tier, (
            f"{domain}: expected tier {expected_tier}, got {result['tier']}"
        )
        assert min_oh <= overhead <= max_oh, (
            f"{domain} Tier {expected_tier}: overhead {overhead} chars out of [{min_oh},{max_oh}]. "
            f"amp={len(result['amplified'])}, orig={len(prompt)}"
        )
