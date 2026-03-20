#!/usr/bin/env python3
"""
DQIII8 — Domain Classifier

Classifies prompts into 5 knowledge domains:
  formal_sciences · natural_sciences · social_sciences
  humanities_arts · applied_sciences

Pipeline:
  1. Keyword match ($0, <1ms) — fast, no network
  2. Embedding similarity via nomic-embed-text ($0, ~50-100ms) — if Ollama available

Usage:
    python3 bin/domain_classifier.py "your prompt"
    python3 bin/domain_classifier.py --setup       # create table + centroids
    python3 bin/domain_classifier.py --setup --force  # recalculate centroids
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, DB_PATH
from embeddings import get_embedding, embedding_to_bytes, bytes_to_embedding, cosine_similarity

EMBED_DIM = 768

DOMAINS: dict[str, dict] = {
    "formal_sciences": {
        "keywords": [
            "mathematics",
            "math",
            "matemáticas",
            "algebra",
            "calculus",
            "logic",
            "lógica",
            "statistics",
            "estadística",
            "probability",
            "theorem",
            "proof",
            "set theory",
            "geometry",
            "geometría",
            "integral",
            "derivative",
            "matrix",
            "eigenvalue",
            "polynomial",
            "regression",
            "hypothesis",
            "p-value",
            "confidence interval",
            "bayesian",
        ],
        "description": "Mathematics, logic, statistics, computation, algorithms, theorems, proofs, probability theory",
    },
    "natural_sciences": {
        "keywords": [
            "physics",
            "física",
            "chemistry",
            "química",
            "biology",
            "biología",
            "ecology",
            "ecología",
            "geology",
            "geología",
            "astronomy",
            "astronomía",
            "quantum",
            "molecular",
            "genetics",
            "evolution",
            "evolución",
            "thermodynamics",
            "electromagnetism",
            # nutrition
            "diet",
            "bmr",
            "tdee",
            "calories",
            "caloric",
            "protein",
            "macros",
            "macronutrient",
            "meal plan",
            "nutrition",
            "vitamins",
            "micronutrient",
            "supplement",
            "body fat",
            "body composition",
            "cholesterol",
            "glycemic",
            # biology
            "cell",
            "dna",
            "gene",
            "crispr",
            "protein folding",
        ],
        "description": "Physics, chemistry, biology, ecology, geology, astronomy, nutrition, diet, BMR, TDEE, meal planning, supplements",
    },
    "social_sciences": {
        "keywords": [
            "economics",
            "economía",
            "economy",
            "psychology",
            "psicología",
            "sociology",
            "sociología",
            "politics",
            "política",
            "anthropology",
            "antropología",
            "demographics",
            "demographic",
            "behavior",
            "comportamiento",
            "policy",
            "governance",
            # marketing
            "google ads",
            "meta ads",
            "facebook ads",
            "seo",
            "sem",
            "campaign",
            "roas",
            "cac",
            "ltv",
            "ctr",
            "funnel",
            "leads",
            "conversion rate",
            "brand",
            "audience targeting",
            "advertising",
            "social media",
            "content marketing",
            "keyword research",
            "ad spend",
            "attribution",
            "landing page",
            "email marketing",
            "search engine",
            "organic traffic",
            "backlinks",
            "domain authority",
            "impressions",
            "click-through",
            "quality score",
            "ad rank",
            # finance
            "var",
            "portfolio",
            "capm",
            "hedge",
            "derivatives",
            "wacc",
            "dcf",
            "p/e",
            "ebitda",
            "bonds",
            "equity",
            "risk management",
            "basel",
            "options",
            "futures",
            "black-scholes",
            "sharpe",
            "volatility",
            # business
            "startup",
            "business plan",
            "revenue model",
            "pricing strategy",
            "b2b",
            "b2c",
            "go-to-market",
            "saas",
            "mrr",
            "arr",
            "churn",
            # law / tenders
            "tender",
            "bid",
            "licitación",
            "lcsp",
            "solvency",
            "solvencia",
            "placsp",
            "contrato público",
            "pliego",
            "adjudicación",
            "rolece",
            "cpv",
            "public contract",
            "public procurement",
            "concurso",
            "contract award",
        ],
        "description": "Economics, psychology, sociology, politics, marketing, SEO, advertising, finance, portfolio management, risk management, business, law, public tenders, procurement",
    },
    "humanities_arts": {
        "keywords": [
            "literature",
            "literatura",
            "philosophy",
            "filosofía",
            "history",
            "historia",
            "art",
            "arte",
            "music",
            "música",
            "language",
            "idioma",
            "linguistics",
            "lingüística",
            "culture",
            "cultura",
            "poetry",
            "poesía",
            "narrative",
            "narrativa",
            "rhetoric",
            "ethics",
            "ética",
        ],
        "description": "Literature, philosophy, history, art, music, linguistics, culture, ethics",
    },
    "applied_sciences": {
        "keywords": [
            "engineering",
            "ingeniería",
            "medicine",
            "medicina",
            "technology",
            "tecnología",
            "architecture",
            "arquitectura",
            "agriculture",
            "agricultura",
            "robotics",
            "networks",
            "redes",
            "hardware",
            "infrastructure",
            "clinical",
            "clínico",
            "manufacturing",
            # programming languages
            "react",
            "typescript",
            "javascript",
            "c++",
            "python",
            "node.js",
            "nodejs",
            "rust",
            "golang",
            "java",
            "kotlin",
            "swift",
            # web / infra
            "html",
            "css",
            "frontend",
            "backend",
            "fullstack",
            "dom",
            "webpack",
            "next.js",
            "nextjs",
            "vite",
            # APIs / protocols
            "rest api",
            "graphql",
            "websocket",
            "grpc",
            # data / infra
            "sql",
            "database",
            "docker",
            "kubernetes",
            "ci/cd",
            "devops",
            "git",
            "microservices",
            "cloud",
            # software concepts
            "algorithm",
            "computation",
            "computación",
            "data structure",
            "parser",
            "compiler",
            "async",
            "concurrency",
            "multithreading",
        ],
        "description": "Engineering, medicine, technology, software development, web development, programming, React, TypeScript, C++, databases, APIs, DevOps, infrastructure",
    },
}


# Embedding helpers are provided by embeddings.py
_get_embedding = get_embedding
_pack_embedding = embedding_to_bytes
_unpack_embedding = bytes_to_embedding
_cosine = cosine_similarity


# ── DB setup ─────────────────────────────────────────────────────────────────


def setup_db(force: bool = False) -> None:
    """Creates the domain_enrichment table and calculates centroids via Ollama."""
    if not DB_PATH.exists():
        print(f"[domain_classifier] DB not found: {DB_PATH}", file=sys.stderr)
        return

    with get_db(timeout=5) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS domain_enrichment (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                description TEXT    NOT NULL,
                keywords    TEXT    NOT NULL,  -- JSON array
                centroid    BLOB,              -- packed float32 embedding
                created_at  TEXT    DEFAULT (datetime('now')),
                updated_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_name ON domain_enrichment (name)")

        for domain_name, info in DOMAINS.items():
            existing = conn.execute(
                "SELECT id, centroid FROM domain_enrichment WHERE name = ?",
                (domain_name,),
            ).fetchone()

            if existing and not force and existing[1] is not None:
                print(f"  ✓ {domain_name} — already has centroid (use --force to recalculate)")
                continue

            # Calculate centroid: embedding of descriptive text + keywords
            centroid_text = info["description"] + ". Keywords: " + ", ".join(info["keywords"])
            print(f"  → Calculating centroid for {domain_name}...", end="", flush=True)
            vec = _get_embedding(centroid_text)

            centroid_blob = _pack_embedding(vec) if vec else None
            status = "✓" if vec else "✗ (Ollama not available — centroid null)"

            if existing:
                conn.execute(
                    "UPDATE domain_enrichment SET description=?, keywords=?, centroid=?, updated_at=datetime('now') WHERE name=?",
                    (info["description"], json.dumps(info["keywords"]), centroid_blob, domain_name),
                )
            else:
                conn.execute(
                    "INSERT INTO domain_enrichment (name, description, keywords, centroid) VALUES (?,?,?,?)",
                    (domain_name, info["description"], json.dumps(info["keywords"]), centroid_blob),
                )
            print(f" {status}")

    print("[domain_classifier] Setup complete.")


# ── Classification ────────────────────────────────────────────────────────────


def _classify_by_keywords(prompt_lower: str) -> str | None:
    """Keyword matching. Returns the domain with the most hits, or None."""
    scores: dict[str, int] = {}
    for domain_name, info in DOMAINS.items():
        hits = sum(1 for kw in info["keywords"] if kw in prompt_lower)
        if hits:
            scores[domain_name] = hits
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def _classify_by_embedding(prompt: str) -> tuple[str, float] | None:
    """
    Embedding similarity against centroids stored in DB.
    Returns (domain_name, score) or None if Ollama / DB not available.
    """
    if not DB_PATH.exists():
        return None

    prompt_vec = _get_embedding(prompt)
    if prompt_vec is None:
        return None

    try:
        with get_db(timeout=2) as conn:
            rows = conn.execute(
                "SELECT name, centroid FROM domain_enrichment WHERE centroid IS NOT NULL"
            ).fetchall()
    except Exception:
        return None

    if not rows:
        return None

    best_name, best_score = "", -1.0
    for name, blob in rows:
        if blob:
            centroid = _unpack_embedding(blob)
            score = _cosine(prompt_vec, centroid)
            if score > best_score:
                best_score, best_name = score, name

    return (best_name, round(best_score, 4)) if best_name else None


def classify_domain(prompt: str) -> tuple[str, float, str]:
    """
    Classifies the domain of the prompt.

    Returns:
        (domain_name, confidence, method)
        method: 'keyword' | 'embedding' | 'default'
    """
    prompt_lower = prompt.lower()

    # 1. Keyword match (fast)
    kw_domain = _classify_by_keywords(prompt_lower)
    if kw_domain:
        return kw_domain, 1.0, "keyword"

    # 2. Embedding similarity (slower)
    emb_result = _classify_by_embedding(prompt)
    if emb_result:
        domain, score = emb_result
        return domain, score, "embedding"

    # 3. Default
    return "applied_sciences", 0.0, "default"


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    args = sys.argv[1:]

    if "--setup" in args:
        force = "--force" in args
        print("─── Domain Enrichment Setup ───")
        setup_db(force=force)
        return

    if not args:
        print('Usage: python3 bin/domain_classifier.py "prompt"', file=sys.stderr)
        print("     python3 bin/domain_classifier.py --setup [--force]", file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(a for a in args if not a.startswith("--"))
    domain, score, method = classify_domain(prompt)
    print(f"domain={domain} score={score:.4f} method={method}")


if __name__ == "__main__":
    main()
