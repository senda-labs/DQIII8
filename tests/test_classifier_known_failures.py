"""
tests/test_classifier_known_failures.py — Domain Classifier Edge Cases

Tracks prompts that previously misclassified due to embedding fallback noise.
Fixed by adding SOLID/design-patterns keywords to applied_sciences and
adjusting the keyword-vs-embedding conflict threshold to 0.55.
"""

import os
import sys
from pathlib import Path

DQIII8_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

os.environ.setdefault("DQIII8_ROOT", str(DQIII8_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(DQIII8_ROOT / ".env")
except ImportError:
    pass

from domain_classifier import classify_domain


def test_wacc_classifies_as_social_sciences():
    """'calculate WACC for Tesla' should route to social_sciences (finance)."""
    domain, confidence, method = classify_domain("calculate WACC for Tesla")
    assert domain == "social_sciences", (
        f"expected social_sciences, got {domain!r} "
        f"(confidence={confidence:.2f}, method={method})"
    )


def test_solid_principles_classifies_as_applied_sciences():
    """'SOLID principles in Python' should route to applied_sciences."""
    domain, confidence, method = classify_domain("SOLID principles in Python")
    assert domain == "applied_sciences", (
        f"expected applied_sciences, got {domain!r} "
        f"(confidence={confidence:.2f}, method={method})"
    )
