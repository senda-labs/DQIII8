#!/usr/bin/env python3
"""
Hierarchical Multi-Centroid Weighted Router (HMCWR) for DQIII8.

3-level classification:
  Level 1: Centroids (Faculty)     — 5 domain centroids, softmax weighted
  Level 2: Agents (Career)         — sub-categories within active centroids
  Level 3: Sub-agents (Specialty)  — specific topics within active agents

Constraints:
  - Max 2 active centroids per task (3rd+ queued as follow-up action)
  - Total latency target: <10ms for classification (excluding embedding call)
  - Knowledge chunks allocated proportional to weights

Math:
  Level 1: w_i = softmax(cosine(E_prompt, C_i) / τ₁)  where τ₁ = 0.15
  Level 2: sub_w_j = w_i × softmax(cosine(E_prompt, S_ij) / τ₂)  where τ₂ = 0.20
  Level 3: spec_w_k = sub_w_j × softmax(cosine(E_prompt, SP_jk) / τ₃)  where τ₃ = 0.25
"""

import hashlib
import json
import math
import os
import struct
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

BIN_DIR = Path(__file__).parent
if str(BIN_DIR) not in sys.path:
    sys.path.insert(0, str(BIN_DIR))

from embeddings import cosine_similarity, get_embedding
from db import get_db

JARVIS = Path(os.environ.get("JARVIS_ROOT", str(BIN_DIR.parent)))
KNOWLEDGE_DIR = JARVIS / "knowledge"

# ── Configuration ─────────────────────────────────────────────────────────

# Temperature controls distribution sharpness (lower = more concentrated)
TAU_1 = 0.15   # Level 1: centroid selection
TAU_2 = 0.20   # Level 2: agent selection within centroid
TAU_3 = 0.25   # Level 3: sub-agent selection within agent

# Activation thresholds
BETA_1 = 0.10  # Minimum weight to activate a centroid
BETA_2 = 0.05  # Minimum weight to activate an agent
BETA_3 = 0.03  # Minimum weight to activate a sub-agent

# Resource limits
MAX_ACTIVE_CENTROIDS = 2   # Max simultaneous centroids (scale to 5 with more RAM)
MAX_KNOWLEDGE_CHUNKS = 8   # Total chunks across all active domains

# Semantic cache for recent classifications
_CLASSIFICATION_CACHE: OrderedDict = OrderedDict()
_CACHE_MAX_SIZE = 256
_CACHE_TTL_SECONDS = 3600  # 1 hour

# ── Domain hierarchy definition ───────────────────────────────────────────
# Each centroid has agents (subdirectories), each agent has knowledge files

DOMAIN_HIERARCHY = {
    "formal_sciences": {
        "description": "Mathematics, logic, computation, statistics",
        "agents": {
            "mathematics": {
                "description": "Algebra, calculus, number theory, geometry",
                "files": ["algebra_fundamentals.md", "calculus_fundamentals.md"],
            },
            "statistics": {
                "description": "Probability, hypothesis testing, regression, Bayesian methods",
                "files": ["probability_fundamentals.md", "hypothesis_testing_fundamentals.md"],
            },
            "algorithms": {
                "description": "Data structures, algorithms, complexity, computation",
                "files": ["algorithms_fundamentals.md", "data_structures_fundamentals.md"],
            },
        },
    },
    "natural_sciences": {
        "description": "Physics, chemistry, biology, earth sciences",
        "agents": {
            "physics": {
                "description": "Mechanics, thermodynamics, electromagnetism, quantum",
                "files": ["mechanics_fundamentals.md", "thermodynamics_fundamentals.md"],
            },
            "chemistry": {
                "description": "Organic, inorganic, biochemistry, materials",
                "files": ["organic_chemistry_fundamentals.md"],
            },
            "biology": {
                "description": "Cell biology, genetics, ecology, evolution",
                "files": ["cell_biology_fundamentals.md"],
            },
        },
    },
    "social_sciences": {
        "description": "Economics, finance, marketing, business, law, psychology",
        "agents": {
            "economics": {
                "description": "Microeconomics, macroeconomics, behavioral economics",
                "files": ["microeconomics_fundamentals.md", "macroeconomics_fundamentals.md"],
            },
            "finance": {
                "description": "Corporate finance, risk management, derivatives, portfolio theory",
                "files": ["corporate_finance_fundamentals.md", "risk_management_fundamentals.md"],
            },
            "marketing": {
                "description": "Digital marketing, SEO, SEM, social media, market analysis",
                "files": ["digital_marketing_fundamentals.md", "market_analysis_fundamentals.md"],
            },
            "business": {
                "description": "Business planning, startup strategy, operations, management",
                "files": ["business_plan_fundamentals.md", "startup_fundamentals.md"],
            },
            "law": {
                "description": "Contract law, regulatory frameworks, compliance",
                "files": ["contract_law_fundamentals.md"],
            },
        },
    },
    "humanities_arts": {
        "description": "Literature, philosophy, history, arts, psychology",
        "agents": {
            "literature": {
                "description": "Narrative, character development, worldbuilding, creative writing",
                "files": ["narrative_fundamentals.md", "character_development_fundamentals.md"],
            },
            "philosophy": {
                "description": "Ethics, logic, epistemology, argumentation",
                "files": ["ethics_fundamentals.md"],
            },
            "history": {
                "description": "Historical method, research, analysis, historiography",
                "files": ["historical_method_fundamentals.md"],
            },
        },
    },
    "applied_sciences": {
        "description": "Software engineering, data engineering, web development, AI/ML",
        "agents": {
            "software_engineering": {
                "description": "Architecture, testing, design patterns, DevOps, CI/CD",
                "files": ["architecture_fundamentals.md", "testing_fundamentals.md"],
            },
            "data_engineering": {
                "description": "Databases, SQL, data pipelines, ETL, warehousing",
                "files": ["database_fundamentals.md"],
            },
            "web_development": {
                "description": "HTML, CSS, JavaScript, React, frontend frameworks, APIs",
                "files": ["html_css_fundamentals.md", "frontend_frameworks_fundamentals.md"],
            },
            "ai_ml": {
                "description": "Prompt engineering, agent design, machine learning, NLP",
                "files": ["prompt_engineering_fundamentals.md"],
            },
        },
    },
}


# ── Core math functions ───────────────────────────────────────────────────

def softmax_with_temperature(scores: list, temperature: float) -> list:
    """Softmax normalization with temperature scaling.
    Lower temperature → sharper distribution (winner takes more).
    Higher temperature → flatter distribution (more uniform)."""
    if not scores:
        return []
    max_score = max(scores)
    scaled = [(s - max_score) / temperature for s in scores]
    exp_scores = [math.exp(s) for s in scaled]
    total = sum(exp_scores)
    if total == 0:
        return [1.0 / len(scores)] * len(scores)
    return [e / total for e in exp_scores]


def allocate_chunks(weights: dict, max_chunks: int) -> dict:
    """Allocate knowledge chunks proportional to weights.
    Ensures at least 1 chunk per active domain."""
    if not weights:
        return {}

    total_weight = sum(weights.values())
    if total_weight == 0:
        return {}

    allocation = {}
    remaining = max_chunks

    for key, weight in sorted(weights.items(), key=lambda x: -x[1]):
        chunks = max(1, round(max_chunks * (weight / total_weight)))
        chunks = min(chunks, remaining)
        if chunks > 0:
            allocation[key] = chunks
            remaining -= chunks
        if remaining <= 0:
            break

    if remaining > 0 and allocation:
        top_key = max(allocation, key=allocation.get)
        allocation[top_key] += remaining

    return allocation


# ── Centroid loading ──────────────────────────────────────────────────────

def load_centroids() -> dict:
    """Load precomputed centroid embeddings from database.
    Note: domain_enrichment table uses 'name' column (not 'domain')."""
    centroids = {}
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT name, centroid FROM domain_enrichment WHERE centroid IS NOT NULL"
            ).fetchall()
            for row in rows:
                name = row[0]
                blob = row[1]
                if blob:
                    n = len(blob) // 4
                    centroids[name] = list(struct.unpack(f"{n}f", blob))
    except Exception:
        pass
    return centroids


def compute_agent_centroid(domain: str, agent: str) -> Optional[list]:
    """Compute agent-level centroid by averaging embeddings of its knowledge files."""
    agent_info = DOMAIN_HIERARCHY.get(domain, {}).get("agents", {}).get(agent)
    if not agent_info:
        return None

    # Try agent-specific index first, then domain-level index
    for index_path in [
        KNOWLEDGE_DIR / domain / agent / "index.json",
        KNOWLEDGE_DIR / domain / "index.json",
    ]:
        if index_path.exists():
            try:
                with open(index_path, encoding="utf-8") as f:
                    chunks = json.load(f)
                break
            except Exception:
                continue
    else:
        return None

    agent_files = set(agent_info.get("files", []))
    relevant_embeddings = []

    for chunk in chunks:
        source = chunk.get("source", chunk.get("file", ""))
        if any(af in source for af in agent_files):
            emb = chunk.get("embedding")
            if isinstance(emb, list) and len(emb) > 0:
                relevant_embeddings.append(emb)

    if not relevant_embeddings:
        return None

    dim = len(relevant_embeddings[0])
    centroid = [0.0] * dim
    for emb in relevant_embeddings:
        for i in range(min(dim, len(emb))):
            centroid[i] += emb[i]
    centroid = [c / len(relevant_embeddings) for c in centroid]

    return centroid


# ── Main classification pipeline ─────────────────────────────────────────

def _cache_key(embedding: list) -> str:
    """Generate cache key from embedding fingerprint (first 20 dims)."""
    fingerprint = str([round(e, 4) for e in embedding[:20]])
    return hashlib.md5(fingerprint.encode()).hexdigest()


def classify_hierarchical(user_input: str, prompt_embedding: list = None) -> dict:
    """
    3-level hierarchical classification.

    Returns:
        {
            "prompt": str,
            "level1": {domain: weight, ...},           # All 5 scores
            "active_centroids": [                       # Max 2
                {
                    "domain": str,
                    "weight": float,
                    "agents": [                         # Level 2
                        {
                            "name": str,
                            "weight": float,
                            "chunks_allocated": int,
                            "knowledge_files": [str],
                        }
                    ]
                }
            ],
            "queued_centroids": [...],                  # 3rd+ centroids (follow-up)
            "total_chunks": int,
            "classification_ms": float,
        }
    """
    t_start = time.perf_counter()

    if prompt_embedding is None:
        try:
            prompt_embedding = get_embedding(user_input)
        except Exception:
            return _fallback_result(user_input)

    if not prompt_embedding:
        return _fallback_result(user_input)

    # ── Level 1: Centroid scoring ─────────────────────────────────────
    centroids = load_centroids()
    if not centroids:
        return _fallback_result(user_input)

    domain_names = sorted(centroids.keys())
    raw_scores = [cosine_similarity(prompt_embedding, centroids[d]) for d in domain_names]
    weights = softmax_with_temperature(raw_scores, TAU_1)

    level1 = {domain_names[i]: round(weights[i], 4) for i in range(len(domain_names))}

    sorted_domains = sorted(level1.items(), key=lambda x: -x[1])

    active = []
    queued = []

    for domain, weight in sorted_domains:
        if weight < BETA_1:
            continue
        if len(active) < MAX_ACTIVE_CENTROIDS:
            active.append((domain, weight))
        else:
            queued.append((domain, weight))

    if not active and sorted_domains:
        active.append(sorted_domains[0])

    # ── Chunk allocation across active centroids ──────────────────────
    active_weights = {d: w for d, w in active}
    chunk_allocation = allocate_chunks(active_weights, MAX_KNOWLEDGE_CHUNKS)

    # ── Level 2: Agent scoring within each active centroid ────────────
    active_centroids = []

    for domain, domain_weight in active:
        domain_info = DOMAIN_HIERARCHY.get(domain, {})
        agents = domain_info.get("agents", {})
        domain_chunks = chunk_allocation.get(domain, 1)

        if not agents:
            active_centroids.append({
                "domain": domain,
                "weight": round(domain_weight, 4),
                "agents": [],
                "chunks_allocated": domain_chunks,
            })
            continue

        agent_names = sorted(agents.keys())
        agent_scores = []

        for agent_name in agent_names:
            agent_centroid = compute_agent_centroid(domain, agent_name)
            if agent_centroid:
                score = cosine_similarity(prompt_embedding, agent_centroid)
            else:
                desc = agents[agent_name].get("description", agent_name)
                try:
                    desc_emb = get_embedding(desc)
                    score = cosine_similarity(prompt_embedding, desc_emb) if desc_emb else 0.0
                except Exception:
                    score = 0.0
            agent_scores.append(score)

        agent_weights = softmax_with_temperature(agent_scores, TAU_2)
        agent_weighted = [domain_weight * aw for aw in agent_weights]

        agent_chunk_weights = {}
        for i, agent_name in enumerate(agent_names):
            if agent_weighted[i] >= BETA_2:
                agent_chunk_weights[agent_name] = agent_weighted[i]

        agent_chunk_alloc = allocate_chunks(agent_chunk_weights, domain_chunks)

        active_agents = []
        for agent_name, chunks in agent_chunk_alloc.items():
            active_agents.append({
                "name": agent_name,
                "weight": round(agent_chunk_weights[agent_name], 4),
                "chunks_allocated": chunks,
                "knowledge_files": agents[agent_name].get("files", []),
            })

        active_centroids.append({
            "domain": domain,
            "weight": round(domain_weight, 4),
            "agents": active_agents,
            "chunks_allocated": domain_chunks,
        })

    t_end = time.perf_counter()
    classification_ms = round((t_end - t_start) * 1000, 2)

    return {
        "prompt": user_input[:200],
        "level1": level1,
        "active_centroids": active_centroids,
        "queued_centroids": [
            {"domain": d, "weight": round(w, 4)} for d, w in queued
        ],
        "total_chunks": MAX_KNOWLEDGE_CHUNKS,
        "classification_ms": classification_ms,
    }


def classify_hierarchical_cached(user_input: str, prompt_embedding: list = None) -> dict:
    """Cached version of classify_hierarchical.
    Returns cached result if a similar query was classified within TTL.
    Cache key is based on first 20 embedding dimensions."""
    if prompt_embedding is None:
        try:
            prompt_embedding = get_embedding(user_input)
        except Exception:
            return _fallback_result(user_input)

    key = _cache_key(prompt_embedding)

    # Check cache
    if key in _CLASSIFICATION_CACHE:
        entry = _CLASSIFICATION_CACHE[key]
        if time.time() - entry["timestamp"] < _CACHE_TTL_SECONDS:
            _CLASSIFICATION_CACHE.move_to_end(key)
            result = dict(entry["result"])
            result["from_cache"] = True
            return result
        else:
            del _CLASSIFICATION_CACHE[key]

    # Classify (cache miss)
    result = classify_hierarchical(user_input, prompt_embedding)
    result["from_cache"] = False

    # Store in cache
    _CLASSIFICATION_CACHE[key] = {"result": dict(result), "timestamp": time.time()}
    if len(_CLASSIFICATION_CACHE) > _CACHE_MAX_SIZE:
        _CLASSIFICATION_CACHE.popitem(last=False)

    return result


def retrieve_knowledge_by_routing(routing_result: dict, prompt_embedding: list = None) -> str:
    """Retrieve knowledge chunks based on hierarchical routing result.
    Returns formatted knowledge text for the amplified prompt."""

    knowledge_parts = []

    for centroid in routing_result.get("active_centroids", []):
        domain = centroid["domain"]

        for agent in centroid.get("agents", []):
            agent_name = agent["name"]
            chunks_to_get = agent["chunks_allocated"]

            chunks = _search_agent_knowledge(
                domain, agent_name, agent["knowledge_files"],
                prompt_embedding, max_chunks=chunks_to_get
            )

            if chunks:
                header = (
                    f"### {domain.replace('_', ' ').title()} "
                    f"> {agent_name.replace('_', ' ').title()}"
                )
                knowledge_parts.append(f"{header}\n{chunks}")

    return "\n\n".join(knowledge_parts)


def _search_agent_knowledge(
    domain: str,
    agent: str,
    files: list,
    prompt_embedding: list,
    max_chunks: int,
) -> str:
    """Search for relevant chunks in an agent's knowledge files."""
    all_chunks = None

    for index_path in [
        KNOWLEDGE_DIR / domain / agent / "index.json",
        KNOWLEDGE_DIR / domain / "index.json",
    ]:
        if index_path.exists():
            try:
                with open(index_path, encoding="utf-8") as f:
                    all_chunks = json.load(f)
                break
            except Exception:
                continue

    if all_chunks is None:
        return ""

    agent_files_set = set(files)
    relevant = []

    for chunk in all_chunks:
        source = chunk.get("source", chunk.get("file", ""))
        if any(af in source for af in agent_files_set):
            emb = chunk.get("embedding")
            if isinstance(emb, list) and prompt_embedding:
                sim = cosine_similarity(prompt_embedding, emb)
                relevant.append((sim, chunk))

    relevant.sort(reverse=True, key=lambda x: x[0])

    result_parts = []
    total_chars = 0
    for sim, chunk in relevant[:max_chunks]:
        if sim < 0.35:
            break
        text = chunk.get("text", "")
        if total_chars + len(text) > 2000:
            break
        section = chunk.get("section", "")
        result_parts.append(f"[{section}] {text}" if section else text)
        total_chars += len(text)

    return "\n".join(result_parts)


def _fallback_result(user_input: str) -> dict:
    """Fallback when classification can't run (no embeddings, no centroids)."""
    return {
        "prompt": user_input[:200],
        "level1": {},
        "active_centroids": [],
        "queued_centroids": [],
        "total_chunks": 0,
        "classification_ms": 0,
    }


# ── CLI + Testing ─────────────────────────────────────────────────────────

def print_routing(result: dict):
    """Pretty print a routing result."""
    print(f"\nInput: {result['prompt']}")
    print(f"Classification time: {result['classification_ms']}ms")

    print("\nLevel 1 — All centroid scores:")
    for domain, weight in sorted(result["level1"].items(), key=lambda x: -x[1]):
        bar = "█" * int(weight * 40) + "░" * (40 - int(weight * 40))
        active = " ◀ ACTIVE" if any(
            c["domain"] == domain for c in result["active_centroids"]
        ) else ""
        queued = " ⏳ QUEUED" if any(
            c["domain"] == domain for c in result["queued_centroids"]
        ) else ""
        print(f"  {domain:20s} {bar} {weight:.3f}{active}{queued}")

    print(f"\nActive centroids ({len(result['active_centroids'])}/{MAX_ACTIVE_CENTROIDS} max):")
    for centroid in result["active_centroids"]:
        print(
            f"\n  +- {centroid['domain']} "
            f"(weight: {centroid['weight']}, chunks: {centroid['chunks_allocated']})"
        )
        for agent in centroid.get("agents", []):
            print(
                f"  +-- {agent['name']} "
                f"(weight: {agent['weight']}, chunks: {agent['chunks_allocated']})"
            )
            for f in agent.get("knowledge_files", []):
                print(f"  |   +-- {f}")

    if result["queued_centroids"]:
        print(f"\nQueued for follow-up ({len(result['queued_centroids'])}):")
        for q in result["queued_centroids"]:
            print(f"  (queued) {q['domain']} (weight: {q['weight']})")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--test":
        test_inputs = [
            "Create a digital marketing agency for cleaning products",
            "Calculate the Value at Risk of a portfolio at 95% confidence",
            "Write chapter 5 where Lin Feng discovers the ancestral artifact",
            "Fix the TypeError in my database manager class",
            "Build a REST API with authentication and rate limiting",
            "Explain how gradient descent works in neural networks",
            "Plan a go-to-market strategy for a SaaS startup",
        ]
        for inp in test_inputs:
            print(f"\n{'=' * 70}")
            result = classify_hierarchical(inp)
            print_routing(result)
        sys.exit(0)

    user_input = " ".join(sys.argv[1:])
    result = classify_hierarchical(user_input)
    print_routing(result)
