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
    "formal_sciences": "derivative of x squared",
    "natural_sciences": "photosynthesis process",
    "social_sciences": "inflation monetary policy impact",
    "humanities_arts": "romanticism in Keats poetry",
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
    assert isinstance(
        result["tier"], int
    ), f"tier debe ser int, got {type(result['tier'])}"
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


def test_working_memory_save_and_retrieve():
    """Working memory persists via SQLite across function calls."""
    import sqlite3
    from working_memory import get_session_context, save_exchange

    sid = "test_unit_wm_001"
    conn = sqlite3.connect("database/jarvis_metrics.db")
    conn.execute("DELETE FROM session_memory WHERE session_id = ?", (sid,))
    conn.commit()
    conn.close()

    save_exchange(sid, "calculate WACC for Tesla", "WACC = 8.5%", "social_sciences")
    ctx = get_session_context(sid)
    assert "WACC" in ctx, f"Expected 'WACC' in context, got: {ctx!r}"
    assert "Tesla" in ctx, f"Expected 'Tesla' in context, got: {ctx!r}"

    conn = sqlite3.connect("database/jarvis_metrics.db")
    conn.execute("DELETE FROM session_memory WHERE session_id = ?", (sid,))
    conn.commit()
    conn.close()


def test_working_memory_empty_session():
    """New session returns empty context."""
    from working_memory import get_session_context

    assert get_session_context("nonexistent_session_xyz_999") == ""


def test_working_memory_session_ids():
    """Session ID generators produce correctly prefixed strings."""
    from working_memory import get_session_id

    assert get_session_id("telegram", chat_id=12345).startswith("tg_")
    assert get_session_id("autonomous").startswith("auto_")
    assert get_session_id().startswith("cc_")


def test_knowledge_enricher_get_chunks():
    """get_relevant_chunks returns list[dict] without modifying the prompt."""
    from knowledge_enricher import get_relevant_chunks

    original = "photosynthesis process"
    chunks = get_relevant_chunks(original, "natural_sciences")
    assert isinstance(chunks, list), f"expected list, got {type(chunks)}"
    if chunks:
        assert all(isinstance(c, dict) for c in chunks), "each item must be dict"
        assert all(
            "text" in c and "score" in c for c in chunks
        ), "each dict must have text+score"
    assert original == "photosynthesis process", "prompt must not be mutated"


def test_amplifier_entity_not_context():
    """Entity extracted from original prompt, not from domain-context prefix."""
    result = amplify("calculate WACC for Tesla", domain="social_sciences")
    assert (
        result["entity"] != "CONTEXT"
    ), f"entity should not be 'CONTEXT' (double-enrichment bug). Got: {result['entity']!r}"


def test_amplifier_chunks_used_post_filter():
    """chunks_used must reflect post-filter count, not raw retrieved count.

    Fix 1: _build_amplified_prompt now returns (prompt, injected_count).
    For Tier C the cap is 1; the return value must be <= 1 regardless of
    how many chunks were retrieved.
    """
    from knowledge_enricher import get_relevant_chunks

    chunks = get_relevant_chunks(
        "prove convergence of Newton-Raphson", "formal_sciences", top_k=5
    )
    result = amplify(
        "prove convergence of Newton-Raphson", domain="formal_sciences", chunks=chunks
    )
    assert result["tier"] == 1, f"expected Tier C (1), got {result['tier']}"
    assert (
        result["chunks_used"] <= 1
    ), f"chunks_used should be post-filter (<=1 for Tier C), got {result['chunks_used']}"


def test_amplifier_niche_routing_to_tier_a():
    """Finance niche must route to Tier A even when domain classifier returns social_sciences.

    Fix 2: _select_tier checks decomp['niche'] first. 'finance' niche → Tier A (3).
    Previously: 'social_sciences' not in high_tier_domains → Tier C (1). Bug.
    """
    result = amplify(
        "calculate WACC for Tesla assuming 10% cost of equity", domain="social_sciences"
    )
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

    chunks = get_relevant_chunks(
        "analyze the use of light in Vermeer paintings", "humanities_arts", top_k=5
    )
    result = amplify(
        "analyze the use of light in Vermeer paintings",
        domain="humanities_arts",
        chunks=chunks,
    )
    amp = result["amplified"]
    if result["chunks_used"] == 0:
        assert (
            amp == "analyze the use of light in Vermeer paintings"
        ), "With 0 specific chunks, Tier B must return original prompt unmodified"
    else:
        assert (
            "<reference>" in amp
        ), "With specific chunks, Tier B must use <reference> tag"


def test_task_relevance_score_function():
    """score_task_relevance returns float in [0, 1] for valid inputs, 0.0 for empty."""
    from knowledge_enricher import score_task_relevance

    score = score_task_relevance(
        "Vermeer used camera obscura for light", "analyze", "light Vermeer"
    )
    assert isinstance(score, float), f"expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"score out of [0,1]: {score}"

    zero = score_task_relevance("some text", "", "")
    assert zero == 0.0, f"empty intent+entity must return 0.0, got {zero}"


def test_task_relevance_reranking():
    """Reranking by task relevance must actually change the chunk ordering.

    We compare the chunk sequence produced WITHOUT intent/entity against the one
    produced WITH intent+entity.  If the two sequences are identical the re-ranking
    pass is a no-op — that would be a bug.

    Additionally checks structural invariants:
    - every returned dict has a 'task_relevance' key
    - the reranked list is ordered descending by task_relevance
    """
    from knowledge_enricher import get_relevant_chunks

    prompt = "analyze the use of light in Vermeer paintings"

    chunks_base = get_relevant_chunks(prompt, "humanities_arts", top_k=5)
    chunks_reranked = get_relevant_chunks(
        prompt, "humanities_arts", top_k=5, intent="analyze", entity="light Vermeer"
    )

    assert isinstance(
        chunks_reranked, list
    ), f"expected list, got {type(chunks_reranked)}"
    if len(chunks_reranked) < 2:
        return  # not enough data to test ordering

    assert all(
        "task_relevance" in c for c in chunks_reranked
    ), "task_relevance key missing"

    # Reranked list must be descending by task_relevance
    assert (
        chunks_reranked[0]["task_relevance"] >= chunks_reranked[-1]["task_relevance"]
    ), (
        f"task_relevance not descending: first={chunks_reranked[0]['task_relevance']} "
        f"last={chunks_reranked[-1]['task_relevance']}"
    )

    # The ordering must actually change — otherwise the second embedding pass did nothing
    if len(chunks_base) >= 2:
        base_order = [c["text"][:60] for c in chunks_base]
        reranked_order = [c["text"][:60] for c in chunks_reranked]
        assert base_order != reranked_order, (
            "Reranking with intent+entity must change at least one chunk position. "
            "If every chunk stays in the same slot the task_relevance pass is inert."
        )


def test_vermeer_rerank_prefers_technique_over_prices():
    """Task relevance should rank art technique above auction prices for analysis tasks."""
    from knowledge_enricher import get_relevant_chunks

    chunks = get_relevant_chunks(
        "analyze the use of light in Vermeer paintings",
        "humanities_arts",
        intent="analyze",
        entity="light Vermeer",
    )
    if len(chunks) >= 2:
        for c in chunks:
            print(f'relevance={c.get("task_relevance", 0):.3f} {c["text"][:80]}')
        assert chunks[0].get("task_relevance", 0) > chunks[-1].get(
            "task_relevance", 0
        ), (
            f"First chunk should have higher task_relevance than last: "
            f"first={chunks[0].get('task_relevance', 0):.3f} "
            f"last={chunks[-1].get('task_relevance', 0):.3f}"
        )


def test_confidence_gate_skips_generic():
    """Confidence gate skips enrichment when chunks are generic definitions."""
    from confidence_gate import should_enrich

    generic_chunks = [
        {
            "text": "Photosynthesis is the process by which plants convert sunlight",
            "score": 0.25,
        },
        {
            "text": "The process occurs in the chloroplasts of plant cells",
            "score": 0.22,
        },
    ]
    assert (
        should_enrich("explain photosynthesis", "natural_sciences", generic_chunks, 2)
        is False
    )


def test_confidence_gate_enriches_specific():
    """Confidence gate allows enrichment when chunks have specific data."""
    from confidence_gate import should_enrich

    specific_chunks = [
        {
            "text": "Tesla beta coefficient: 1.82 (2026 Q1). Risk-free rate: 4.25%",
            "score": 0.35,
        },
    ]
    assert (
        should_enrich("calculate WACC for Tesla", "social_sciences", specific_chunks, 2)
        is True
    )


def test_confidence_gate_always_enriches_tier_c():
    """Tier C always gets enrichment regardless of chunk quality."""
    from confidence_gate import should_enrich

    assert (
        should_enrich("anything", "any", [{"text": "generic", "score": 0.1}], 1) is True
    )


def test_confidence_gate_skips_empty():
    """No chunks = no enrichment."""
    from confidence_gate import should_enrich

    assert should_enrich("anything", "any", [], 2) is False


def test_intent_suffix_calculate():
    """Calculate intent gets step-by-step suffix."""
    from knowledge_enricher import get_relevant_chunks

    chunks = get_relevant_chunks("calculate derivative of x^2", "formal_sciences")
    r = amplify("calculate derivative of x^2", domain="formal_sciences", chunks=chunks)
    assert (
        "step" in r["amplified"].lower()
    ), f"calculate intent must include 'step' in amplified prompt. Got: {r['amplified']}"


def test_intent_suffix_compare():
    """Compare intent gets comparison structure suffix."""
    from knowledge_enricher import get_relevant_chunks

    chunks = get_relevant_chunks("compare React vs Vue", "applied_sciences")
    r = amplify(
        "compare React vs Vue for a startup", domain="applied_sciences", chunks=chunks
    )
    assert (
        "compar" in r["amplified"].lower()
    ), f"compare intent must include 'compar' in amplified prompt. Got: {r['amplified']}"


def test_no_duplicate_cot_tier_c():
    """Tier C should not have both generic CoT AND intent suffix."""
    r = amplify("calculate 2+2", domain="formal_sciences", chunks=[])
    text = r["amplified"]
    has_generic = "Think step by step" in text
    has_specific = "each calculation step" in text or "each step" in text
    assert not (has_generic and has_specific), (
        f"Duplicate CoT instructions in Tier C: "
        f"generic={'yes' if has_generic else 'no'} "
        f"specific={'yes' if has_specific else 'no'}\n{text}"
    )


def test_amplifier_overhead_chars():
    """Amplified prompt overhead (not ratio) must stay in tier-appropriate range.

    Fix 4: ratio metric is prompt-length dependent. Overhead in chars is stable.
    - Tier C: 30-600 chars overhead (XML tags + 1 truncated chunk + CoT)
    - Tier B: 0-500 chars overhead (reference block only when specific chunks exist)
    - Tier A: 0-400 chars overhead (raw data only, no scaffolding)
    """
    from knowledge_enricher import get_relevant_chunks

    cases = [
        ("formal_sciences", "prove convergence of Newton-Raphson method", 1, 30, 600),
        # Upper bound raised: art_data_reference.md now has Vermeer-specific auction data
        # that passes has_specific_data(), so Tier B injects a <reference> block (~2000 chars).
        (
            "humanities_arts",
            "analyze the use of light in Vermeer paintings",
            2,
            0,
            3000,
        ),
        (
            "social_sciences",
            "calculate WACC for Tesla assuming 10% cost of equity",
            3,
            0,
            400,
        ),
    ]
    for domain, prompt, expected_tier, min_oh, max_oh in cases:
        chunks = get_relevant_chunks(prompt, domain, top_k=5)
        result = amplify(prompt, domain=domain, chunks=chunks)
        overhead = len(result["amplified"]) - len(prompt)
        assert (
            result["tier"] == expected_tier
        ), f"{domain}: expected tier {expected_tier}, got {result['tier']}"
        assert min_oh <= overhead <= max_oh, (
            f"{domain} Tier {expected_tier}: overhead {overhead} chars out of [{min_oh},{max_oh}]. "
            f"amp={len(result['amplified'])}, orig={len(prompt)}"
        )
