#!/usr/bin/env python3
"""
DQIII8 — Subdomain Classifier

Maps prompts to one of 20+ subdomain labels within the 5 parent domains.
Used for role assignment ("You are an expert in {subdomain}") — more precise
than "You are an expert in social_sciences".

Approach: keyword matching, zero latency, no network calls.
Falls back to parent domain if no subdomain matches.

Usage:
    from subdomain_classifier import classify_subdomain
    sd = classify_subdomain("calculate WACC for Tesla", "social_sciences")
    # → "corporate_finance"
"""

from __future__ import annotations

# Subdomain definitions: {parent_domain: {subdomain: [keywords]}}
# Multi-word keywords score 2 (high specificity), single-word score 1.
_SUBDOMAINS: dict[str, dict[str, list[str]]] = {
    "formal_sciences": {
        "quantitative_finance": [
            "kelly criterion",
            "black-scholes",
            "black scholes",
            "options pricing",
            "derivatives pricing",
            "binomial tree",
            "monte carlo simulation",
            "stochastic",
            "brownian motion",
            "risk-neutral",
            "put-call parity",
            "greeks",
            "delta hedge",
        ],
        "algorithms": [
            "big-o",
            "big o",
            "time complexity",
            "space complexity",
            "sorting algorithm",
            "merge sort",
            "quicksort",
            "binary search",
            "dynamic programming",
            "graph algorithm",
            "bfs",
            "dfs",
            "amortized",
            "convergence rate",
            "newton-raphson",
            "data structure",
            "hash table",
            "binary tree",
        ],
        "statistics": [
            "hypothesis test",
            "p-value",
            "confidence interval",
            "t-test",
            "chi-square",
            "anova",
            "regression",
            "correlation",
            "bayesian",
            "prior",
            "posterior",
            "likelihood",
            "standard deviation",
            "variance",
            "distribution",
        ],
        "mathematics": [
            "calculus",
            "integral",
            "derivative",
            "differential equation",
            "linear algebra",
            "matrix",
            "eigenvalue",
            "vector space",
            "proof",
            "theorem",
            "lemma",
            "axiom",
            "number theory",
            "prime",
            "modular arithmetic",
        ],
    },
    "natural_sciences": {
        "nutrition": [
            "bmr",
            "tdee",
            "basal metabolic rate",
            "katch-mcardle",
            "calories",
            "macronutrient",
            "protein intake",
            "body fat",
            "meal plan",
            "weight loss",
            "diet",
            "macro split",
        ],
        "molecular_biology": [
            "mrna",
            "dna replication",
            "crispr",
            "gene editing",
            "protein folding",
            "alphafold",
            "amino acid",
            "transcription",
            "translation",
            "codon",
            "vaccine mechanism",
            "antibody",
            "immune response",
        ],
        "physics": [
            "quantum mechanics",
            "relativity",
            "thermodynamics",
            "electromagnetism",
            "wave function",
            "schrodinger",
            "boltzmann",
            "planck constant",
            "speed of light",
            "gravitational",
            "entropy",
            "enthalpy",
        ],
        "chemistry": [
            "pka",
            "buffer solution",
            "titration",
            "molar",
            "reaction kinetics",
            "gibbs free energy",
            "oxidation",
            "reduction",
            "periodic table",
            "bond energy",
        ],
    },
    "social_sciences": {
        "corporate_finance": [
            "wacc",
            "weighted average cost of capital",
            "dcf",
            "discounted cash flow",
            "ebitda",
            "p/e ratio",
            "valuation",
            "cost of equity",
            "cost of debt",
            "capm",
            "beta coefficient",
            "equity premium",
        ],
        "macroeconomics": [
            "fiscal policy",
            "monetary policy",
            "inflation rate",
            "gdp",
            "interest rate",
            "taylor rule",
            "is-lm",
            "fiscal multiplier",
            "phillips curve",
            "nairu",
            "quantitative easing",
            "central bank",
        ],
        "strategy": [
            "porter five forces",
            "competitive advantage",
            "swot",
            "market positioning",
            "value chain",
            "business model",
            "go-to-market",
            "competitive strategy",
            "moat",
        ],
        # distributed_systems lives here because the parent domain_classifier routes
        # "CAP theorem", "consensus", etc. to social_sciences by default (no AS keyword match).
        # Role: "expert in distributed_systems" is more accurate than "expert in social_sciences".
        "distributed_systems": [
            "cap theorem",
            "partition tolerance",
            "consensus",
            "raft",
            "paxos",
            "eventual consistency",
            "distributed",
            "fault tolerance",
        ],
        "marketing": [
            "seo",
            "google ads",
            "meta ads",
            "roas",
            "cac",
            "ltv",
            "conversion rate",
            "funnel",
            "audience targeting",
            "content marketing",
            "brand positioning",
        ],
    },
    "humanities_arts": {
        "philosophy": [
            "stoic",
            "epicurean",
            "stoicism",
            "epicureanism",
            "utilitarianism",
            "kantian",
            "deontology",
            "virtue ethics",
            "existential",
            "phenomenology",
            "rawls",
            "trolley problem",
            "ethics",
            "moral philosophy",
            "free will",
        ],
        "design": [
            "bauhaus",
            "typography",
            "color theory",
            "grid system",
            "ux design",
            "ui design",
            "visual hierarchy",
            "gestalt",
            "modernism",
            "art deco",
        ],
        "linguistics": [
            "sapir-whorf",
            "sapir whorf",
            "linguistic relativity",
            "morphology",
            "syntax",
            "semantics",
            "phonology",
            "language acquisition",
            "cognitive linguistics",
        ],
        "film_narrative": [
            "narrative structure",
            "three act",
            "screenplay",
            "christopher nolan",
            "nonlinear narrative",
            "editing",
            "cinematography",
            "mise-en-scene",
            "auteur",
        ],
    },
    "applied_sciences": {
        "ai_ml": [
            "rag",
            "retrieval augmented",
            "llm",
            "large language model",
            "transformer",
            "embedding",
            "fine-tuning",
            "fine-tune",
            "prompt engineering",
            "chain of thought",
            "few-shot",
            "vector store",
            "neural network",
            "deep learning",
            "nlp",
            "natural language processing",
            "sentiment analysis",
            "tokenization",
            "named entity",
            "text classification",
            "procesamiento de lenguaje",
            "análisis de sentimiento",
        ],
        "devops": [
            "docker",
            "kubernetes",
            "ci/cd",
            "continuous integration",
            "continuous deployment",
            "terraform",
            "ansible",
            "microservices",
            "service mesh",
            "observability",
        ],
        "web_dev": [
            "react",
            "typescript",
            "javascript",
            "next.js",
            "rest api",
            "graphql",
            "frontend",
            "backend",
            "websocket",
            "oauth",
            "jwt",
            "cors",
        ],
        "databases": [
            "sql",
            "window function",
            "query plan",
            "index",
            "postgresql",
            "nosql",
            "mongodb",
            "redis",
            "normalization",
            "transaction",
            "acid",
        ],
    },
}


def classify_subdomain(prompt: str, domain: str) -> str:
    """Return the most specific subdomain for this prompt within the given domain.

    Uses weighted keyword matching (multi-word = 2pts, single-word = 1pt).
    Falls back to the parent domain name if no subdomain matches.

    Args:
        prompt: original user prompt
        domain: parent domain from domain_classifier (e.g. 'social_sciences')

    Returns:
        subdomain string (e.g. 'corporate_finance') or domain as fallback
    """
    subdomain_map = _SUBDOMAINS.get(domain)
    if not subdomain_map:
        return domain

    prompt_lower = prompt.lower()
    scores: dict[str, int] = {}

    for subdomain, keywords in subdomain_map.items():
        hits = 0
        for kw in keywords:
            kw_lower = kw.lower()
            if " " in kw_lower:
                # Multi-word: 2 points (high specificity)
                if kw_lower in prompt_lower:
                    hits += 2
            else:
                # Single word: 1 point
                if kw_lower in prompt_lower:
                    hits += 1
        scores[subdomain] = hits

    # Tie: first subdomain with max score wins (Python dict insertion order)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return domain  # fallback: no keyword matched
    return best


if __name__ == "__main__":
    test_cases = [
        ("calculate WACC for Tesla", "social_sciences"),
        ("what is time complexity of merge sort", "formal_sciences"),
        ("explain RAG architecture and embeddings", "applied_sciences"),
        ("compare Stoic and Epicurean ethics", "humanities_arts"),
        ("calculate BMR using Katch-McArdle formula", "natural_sciences"),
        ("explain CAP theorem consistency tradeoffs", "social_sciences"),
        ("derive Black-Scholes pricing formula", "formal_sciences"),
    ]
    for prompt, domain in test_cases:
        sd = classify_subdomain(prompt, domain)
        print(f"  {domain:20s} → {sd:25s} | {prompt[:50]}")
