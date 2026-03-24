"""
tests/test_domain_agent_selector.py — Unit tests for domain_agent_selector.py

Tests:
  1. Finance keyword match → finance-specialist
  2. Python keyword match → python-specialist (applied_sciences)
  3. Unknown domain → ("default", "")
  4. No trigger match → ("default", domain_default_system)
  5. Latency < 1ms for repeated calls (cache hit)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

DQIII8_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

from domain_agent_selector import invalidate_cache, select_domain_agent  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure each test starts with a fresh cache load."""
    invalidate_cache()
    yield
    invalidate_cache()


def test_finance_keyword_match():
    """Prompt with WACC + DCF should select finance-specialist in social_sciences."""
    agent, system = select_domain_agent(
        "Calcula el WACC y el DCF para valorar esta empresa", "social_sciences"
    )
    assert agent == "finance-specialist", f"Expected finance-specialist, got {agent}"
    assert len(system) > 10, "Expected non-empty system prompt"


def test_python_keyword_match():
    """Prompt with 'traceback' + 'async' should select python-specialist."""
    agent, system = select_domain_agent(
        "I have a Python traceback with async generator exception", "applied_sciences"
    )
    assert agent == "python-specialist", f"Expected python-specialist, got {agent}"
    assert len(system) > 10, "Expected non-empty system prompt"


def test_unknown_domain_returns_empty():
    """Domain not in map → ('default', '')."""
    agent, system = select_domain_agent("anything", "nonexistent_domain")
    assert agent == "default"
    assert system == ""


def test_no_trigger_match_returns_domain_default():
    """Prompt with no matching keywords → ('default', domain default_system)."""
    agent, system = select_domain_agent(
        "hello world", "formal_sciences"  # no math/algo/stats triggers
    )
    assert agent == "default"
    # domain default_system should still be returned
    assert (
        "formal" in system.lower() or len(system) > 0
    ), "Expected domain default_system when no trigger matches"


def test_cache_latency_under_1ms():
    """Second call (cache hit) must complete in < 1ms."""
    # Prime the cache
    select_domain_agent("WACC valuation", "social_sciences")

    start = time.perf_counter()
    for _ in range(100):
        select_domain_agent("WACC valuation", "social_sciences")
    elapsed_ms = (time.perf_counter() - start) * 1000

    avg_ms = elapsed_ms / 100
    assert avg_ms < 1.0, f"Cache hit avg {avg_ms:.3f}ms exceeds 1ms threshold"
