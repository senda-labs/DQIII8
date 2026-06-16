"""
tests/conftest.py — DQIII8 pytest configuration

Defines marks and fixtures so that new users can run:
  python3 -m pytest tests/test_smoke.py -v
without failures caused by optional dependencies not yet configured.

Marks:
  @pytest.mark.requires_ollama  — test needs Ollama + bge-m3 running
  @pytest.mark.requires_db      — test needs dqiii8.db initialized
"""

import os
import subprocess
import uuid
import pytest


@pytest.fixture(autouse=True)
def isolate_session_id(monkeypatch):
    """Give each test a unique session ID so repeated DENY decisions don't
    accumulate in the production DB and trigger _check_repeat_rejections.
    SESSION_ID is captured at module import time, so we patch the variable
    directly rather than relying on the env var being re-read."""
    import sys
    unique_id = f"pytest-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("CLAUDE_SESSION_ID", unique_id)
    # Patch the module-level constant that was already read at import time
    pa_mod = sys.modules.get("permission_analyzer")
    if pa_mod is not None:
        monkeypatch.setattr(pa_mod, "SESSION_ID", unique_id)


@pytest.fixture
def anyio_backend():
    """Pin anyio-marked async tests to asyncio — trio is not installed on the VPS."""
    return "asyncio"


def _ollama_available() -> bool:
    """Return True if Ollama is reachable and bge-m3 is present."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "bge-m3" in result.stdout
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_ollama: mark test as requiring Ollama + bge-m3 to be running",
    )
    config.addinivalue_line(
        "markers",
        "requires_db: mark test as requiring an initialized dqiii8.db",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip Ollama-dependent tests when Ollama is not available."""
    if _ollama_available():
        return  # All good — run everything

    skip_ollama = pytest.mark.skip(
        reason="Ollama not running or bge-m3 not pulled. "
        "Run: ollama pull bge-m3 && ollama serve"
    )
    # Tests that require Ollama (embeddings, knowledge enrichment, domain centroids)
    ollama_tests = {
        "test_domain_classifier",
        "test_knowledge_enricher",
        "test_intent_amplifier",
        "test_embeddings",
        "test_knowledge_enricher_get_chunks",
        "test_amplifier_entity_not_context",
        "test_amplifier_chunks_used_post_filter",
        "test_amplifier_niche_routing_to_tier_a",
        "test_amplifier_tier_b_no_reference_when_no_specific_chunks",
        "test_task_relevance_reranking",
        "test_vermeer_rerank_prefers_technique_over_prices",
        "test_intent_suffix_calculate",
        "test_intent_suffix_compare",
        "test_no_duplicate_cot_tier_c",
        "test_amplifier_overhead_chars",
        "test_gate_integrated_blocks_low_sim_chunks_tier_a",
        "test_cot_applied_to_tier_b_formula",
        "test_domain_lens_uses_subdomain_for_wacc",
        "test_domain_lens_uses_subdomain_for_algorithms",
    }
    for item in items:
        if item.name in ollama_tests or item.get_closest_marker("requires_ollama"):
            item.add_marker(skip_ollama)
