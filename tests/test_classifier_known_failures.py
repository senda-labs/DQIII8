"""
tests/test_classifier_known_failures.py — Domain Classifier Known Failures

Tracks prompts that misclassify due to embedding fallback noise.
These tests are marked xfail(strict=False): they currently FAIL (expected),
and will auto-promote to PASS once the classifier embedding is fixed.

Bug: domain_classifier embedding fallback misclassifies finance and
     software-design prompts when keyword matching produces no strong hit.

Backlog: "domain_classifier embedding fallback misclassifies finance and
          code prompts — WACC→formal_sciences, SOLID→humanities_arts"
"""
import os
import sys
from pathlib import Path

import pytest

DQIII8_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

os.environ.setdefault("DQIII8_ROOT", str(DQIII8_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(DQIII8_ROOT / ".env")
except ImportError:
    pass

from domain_classifier import classify_domain


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Embedding fallback misclassifies finance prompt as formal_sciences "
        "(confidence ~0.53). Expected social_sciences. Fix: retrain or "
        "add finance keywords to domain_classifier keyword map."
    ),
)
def test_wacc_classifies_as_social_sciences():
    """'calculate WACC for Tesla' should route to social_sciences (finance)."""
    domain, confidence, method = classify_domain("calculate WACC for Tesla")
    assert domain == "social_sciences", (
        f"expected social_sciences, got {domain!r} "
        f"(confidence={confidence:.2f}, method={method})"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Embedding fallback misclassifies software-design prompt as "
        "humanities_arts (confidence ~0.60). Expected applied_sciences. "
        "Fix: add SOLID/design-patterns keywords to applied_sciences keyword map."
    ),
)
def test_solid_principles_classifies_as_applied_sciences():
    """'SOLID principles in Python' should route to applied_sciences."""
    domain, confidence, method = classify_domain("SOLID principles in Python")
    assert domain == "applied_sciences", (
        f"expected applied_sciences, got {domain!r} "
        f"(confidence={confidence:.2f}, method={method})"
    )
