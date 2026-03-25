#!/usr/bin/env python3
"""ML-based tier selector for DQ pipeline.

Phase 1: heuristic rules (no ML model needed)
Phase 2: Random Forest trained on routing_feedback (500+ rows)
Phase 3: RF retrained weekly with feedback loop (2000+ rows)
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import logging
log = logging.getLogger(__name__)
DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = DQIII8_ROOT / "database" / "jarvis_metrics.db"
MODEL_PATH = DQIII8_ROOT / "models" / "tier_predictor.pkl"

CODE_KEYWORDS = {
    "python", "function", "class", "error", "traceback", "refactor",
    "debug", "test", "import", "async", "def ", "git ", "npm", "pip",
    "dockerfile", "yaml", "json", "sql", "bash", "script"
}

COMPLEX_KEYWORDS = {
    "architecture", "design system", "multi-step", "orchestrate",
    "compare and contrast", "analyze in depth", "write a complete",
    "full implementation", "business plan", "investment strategy",
    "research paper", "comprehensive report"
}

DOMAIN_KEYWORDS = {
    "natural_sciences": {"bmr", "tdee", "calories", "protein", "dna",
                         "molecule", "force", "energy", "evolution"},
    "social_sciences": {"wacc", "dcf", "var", "portfolio", "gdp",
                        "inflation", "contract", "seo", "marketing"},
    "formal_sciences": {"derivative", "integral", "algorithm", "proof",
                        "theorem", "matrix", "complexity"},
    "humanities_arts": {"chapter", "scene", "character", "philosophy",
                        "century", "war", "ethics"},
    "applied_sciences": {"python", "react", "api", "docker", "database",
                         "frontend", "backend", "devops"}
}


def predict_tier(prompt: str) -> int:
    """Predict optimal tier for a prompt.

    Returns: 1 (Tier C local), 2 (Tier B Groq), 3 (Tier A Sonnet)
    """
    if MODEL_PATH.exists():
        try:
            import pickle
            with open(MODEL_PATH, "rb") as f:
                model = pickle.load(f)
            features = extract_features(prompt)
            return int(model.predict([features])[0])
        except Exception as _exc:
            log.warning('%s: %s', __name__, _exc)

    prompt_lower = prompt.lower()

    code_hits = sum(1 for kw in CODE_KEYWORDS if kw in prompt_lower)
    if code_hits >= 2:
        return 1

    if any(kw in prompt_lower for kw in COMPLEX_KEYWORDS):
        return 3

    if len(prompt) > 500:
        domain_hits = sum(
            1 for domain_kws in DOMAIN_KEYWORDS.values()
            for kw in domain_kws if kw in prompt_lower
        )
        if domain_hits >= 3:
            return 3

    return 2


def extract_features(prompt: str) -> list:
    """Extract feature vector for ML model (Phase 2+)."""
    prompt_lower = prompt.lower()
    return [
        len(prompt),
        sum(1 for kw in CODE_KEYWORDS if kw in prompt_lower),
        sum(1 for kw in COMPLEX_KEYWORDS if kw in prompt_lower),
        sum(1 for kws in DOMAIN_KEYWORDS.values() for kw in kws if kw in prompt_lower),
        1 if len(prompt) > 500 else 0,
        prompt_lower.count("?"),
        prompt_lower.count("\n"),
    ]


def get_training_data_count() -> int:
    """Count rows in routing_feedback for phase determination."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute(
            "SELECT COUNT(*) FROM routing_feedback"
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description="DQ Smart Tier Selector")
    parser.add_argument("--predict", type=str, help="Predict tier for prompt")
    parser.add_argument("--status", action="store_true", help="Show selector status")
    parser.add_argument("--train", action="store_true", help="Train RF model (Phase 2+)")
    args = parser.parse_args()

    if args.predict:
        tier = predict_tier(args.predict)
        print(tier)

    elif args.status:
        data_count = get_training_data_count()
        has_model = MODEL_PATH.exists()
        if has_model:
            phase = "Phase 3 (trained RF, retrained weekly)"
        elif data_count >= 500:
            phase = "Phase 2 (enough data, run --train)"
        else:
            phase = f"Phase 1 (heuristic, {data_count}/500 datapoints)"
        print(f"Smart Selector: {phase}")
        print(f"Model exists: {has_model}")
        print(f"Training data: {data_count} rows")

    elif args.train:
        data_count = get_training_data_count()
        if data_count < 500:
            print(f"Not enough data: {data_count}/500 minimum")
            sys.exit(1)
        print("Training not yet implemented — Phase 2 pending")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
