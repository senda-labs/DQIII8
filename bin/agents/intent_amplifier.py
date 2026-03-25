"""
Intent Amplifier v1
===================
6-phase pipeline that enriches a raw user prompt with domain knowledge,
intent pattern analysis, and morphological decomposition before it reaches
the model. Reduces ambiguity and improves response precision.

Phases:
  1. Morphological decomposition — ACTION + ENTITY + NICHE
  2. Multi-centroid domain scoring — find closest domain(s)
  3. Intent pattern matching — classify against 14 patterns
  4. Knowledge retrieval — pull top-k chunks from domain index
  5. Prompt construction — build amplified prompt
  6. Tier selection — route to cheapest tier that can handle the task

Usage:
    from intent_amplifier import amplify
    result = amplify("analiza el WACC de Apple y genera reporte ejecutivo")

    python3 bin/intent_amplifier.py --test
    python3 bin/intent_amplifier.py "tu prompt aqui"
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
for _d in [
    JARVIS / "bin" / s for s in ["", "core", "agents", "monitoring", "tools", "ui"]
]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from db import get_db
from embeddings import bytes_to_embedding, cosine_similarity, get_embedding


def load_env() -> None:
    """Load .env into os.environ (setdefault — does not overwrite existing vars)."""
    env = JARVIS / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


# ── Intent patterns (14) ──────────────────────────────────────────────────────

INTENT_PATTERNS: list[dict] = [
    {
        "id": "analyze",
        "keywords": ["analiza", "analyze", "review", "evalua", "assess"],
        "tier": 2,
    },
    {
        "id": "generate",
        "keywords": ["genera", "generate", "crea", "create", "produce", "write"],
        "tier": 1,
    },
    {
        "id": "optimize",
        "keywords": ["optimiza", "optimize", "mejora", "improve", "refactor"],
        "tier": 1,
    },
    {
        "id": "debug",
        "keywords": ["debug", "fix", "corrige", "error", "falla", "bug"],
        "tier": 1,
    },
    {
        "id": "research",
        "keywords": ["investiga", "research", "busca", "find", "discover"],
        "tier": 2,
    },
    {
        "id": "summarize",
        "keywords": ["resume", "summarize", "condensa", "sintetiza", "brief"],
        "tier": 1,
    },
    {
        "id": "compare",
        "keywords": ["compara", "compare", "diferencia", "vs", "versus"],
        "tier": 2,
    },
    {
        "id": "forecast",
        "keywords": ["predice", "forecast", "proyecta", "project", "estima"],
        "tier": 3,
    },
    {
        "id": "explain",
        "keywords": ["explica", "explain", "describe", "clarifica", "define"],
        "tier": 1,
    },
    {
        "id": "transform",
        "keywords": ["convierte", "transform", "traduce", "translate", "migra"],
        "tier": 1,
    },
    {
        "id": "validate",
        "keywords": ["valida", "validate", "verifica", "verify", "check"],
        "tier": 1,
    },
    {
        "id": "plan",
        "keywords": ["planifica", "plan", "diseña", "design", "architect"],
        "tier": 3,
    },
    {
        "id": "automate",
        "keywords": ["automatiza", "automate", "pipeline", "schedule", "cron"],
        "tier": 1,
    },
    {
        "id": "report",
        "keywords": ["reporte", "report", "informe", "dashboard", "executive"],
        "tier": 3,
    },
]

# Tier labels for logging
TIER_LABELS = {1: "local/Ollama", 2: "Groq/free", 3: "Claude/paid"}

# ── Phase 1: Morphological decomposition ─────────────────────────────────────


def _decompose(prompt: str) -> dict:
    """
    Extracts ACTION + ENTITY + NICHE from a prompt using keyword heuristics.
    Returns {'action': str, 'entity': str, 'niche': str, 'tokens': list[str]}.
    """
    tokens = prompt.lower().split()

    action = ""
    for pattern in INTENT_PATTERNS:
        for kw in pattern["keywords"]:
            if kw in tokens or any(
                t.startswith(kw[:5]) for t in tokens if len(kw) >= 5
            ):
                action = pattern["id"]
                break
        if action:
            break

    # Entity: first capitalized word or noun-like token (heuristic)
    entity = ""
    for tok in prompt.split():
        if (
            tok[0].isupper()
            and len(tok) > 2
            and tok.lower()
            not in {
                "el",
                "la",
                "los",
                "las",
                "un",
                "una",
                "the",
                "a",
                "an",
            }
        ):
            entity = tok
            break

    # Fallback: if no capitalized token found (all-lowercase prompt),
    # use the longest meaningful token as entity candidate.
    if not entity:
        _stopwords = {
            "para",
            "como",
            "sobre",
            "desde",
            "entre",
            "tiene",
            "puede",
            "what",
            "how",
            "the",
            "this",
            "that",
            "with",
            "from",
            "into",
            "when",
            "where",
            "which",
            "analiza",
            "analyze",
            "calcula",
            "calculate",
            "explain",
            "explica",
            "genera",
            "generate",
        }
        candidates = [
            t for t in prompt.lower().split() if len(t) > 4 and t not in _stopwords
        ]
        if candidates:
            entity = max(candidates, key=len)

    # Niche: domain-specific signals
    niche_signals = {
        "finance": ["wacc", "dcf", "ebitda", "roi", "irr", "npv", "balance", "p&l"],
        "trading": ["btc", "eth", "binance", "momentum", "backtest", "sharpe", "garch"],
        "code": ["python", "script", "function", "class", "api", "endpoint", "test"],
        "video": ["reel", "video", "subtitle", "tts", "audio", "elevenlabs", "ffmpeg"],
        "writing": ["novel", "chapter", "scene", "dialogue", "narrative", "story"],
        "data": ["pandas", "dataframe", "csv", "sql", "query", "chart", "plot"],
    }
    niche = ""
    lowered = prompt.lower()
    for n, signals in niche_signals.items():
        # Use word-boundary match to prevent false positives on substrings
        # e.g. "eth" must not match "method", "btc" must not match "abstract"
        if any(re.search(r"\b" + re.escape(s) + r"\b", lowered) for s in signals):
            niche = n
            break

    return {"action": action, "entity": entity, "niche": niche, "tokens": tokens}


# ── Phase 2: Multi-centroid domain scoring ────────────────────────────────────


def _score_domains(prompt: str, top_n: int = 3) -> list[dict]:
    """
    Compares prompt embedding against domain centroids in DB.
    Returns top_n domains sorted by cosine similarity.
    """
    embedding = get_embedding(prompt)
    if not embedding:
        return []

    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT name, centroid FROM domain_enrichment WHERE centroid IS NOT NULL"
            ).fetchall()
    except Exception:
        return []

    scored = []
    for row in rows:
        if not row[1]:
            continue
        try:
            centroid = bytes_to_embedding(row[1])
            score = cosine_similarity(embedding, centroid)
            scored.append({"domain": row[0], "score": round(score, 4)})
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


# ── Phase 3: Intent pattern matching ─────────────────────────────────────────


def _match_intent(tokens: list[str], prompt_lower: str) -> dict:
    """
    Scores each intent pattern and returns the best match plus suggested tier.
    """
    best = {"id": "explain", "score": 0, "tier": 1}
    for pattern in INTENT_PATTERNS:
        score = sum(
            1
            for kw in pattern["keywords"]
            if kw in prompt_lower
            or any(t.startswith(kw[:5]) for t in tokens if len(kw) >= 5)
        )
        if score > best["score"]:
            best = {"id": pattern["id"], "score": score, "tier": pattern["tier"]}
    return best


# ── Phase 4: Knowledge retrieval ─────────────────────────────────────────────


def _retrieve_knowledge(agent_name: str, query: str, top_k: int = 3) -> list[str]:
    """
    Pulls top-k knowledge chunks for agent_name relevant to query.
    Returns list of chunk texts (empty list if index missing).
    """
    try:
        from knowledge_search import search

        results = search(agent_name, query, top_k=top_k)
        return [r["text"] for r in results if r.get("text")]
    except Exception:
        return []


# ── Tier-specific chunk filtering ────────────────────────────────────────────


_DEFINITION_PATTERNS = (
    "is defined as",
    "refers to",
    "is the process of",
    "is a type of",
    "is a method of",
    "is the study of",
    "is an approach",
)


def has_specific_data(text: str) -> bool:
    """True if chunk contains specific/numerical/recent data vs generic definitions.

    Requires 3+ positive indicators (raised from 2) to reduce false positives
    from domain-specific but off-topic chunks (e.g. biochemistry tables for a
    photosynthesis query).  Also returns False for definition-style text.
    """
    tl = text.lower()
    if any(pat in tl for pat in _DEFINITION_PATTERNS):
        return False
    indicators = [
        any(ch.isdigit() for ch in text),
        any(yr in text for yr in ["2024", "2025", "2026"]),
        any(sym in text for sym in ["%", "$", "€"]),
        "|" in text,  # table data
        any(op in text for op in ["=", "→", "±", "≈", "≤", "≥"]),  # equations
    ]
    return sum(indicators) >= 3


def filter_chunks_for_tier(chunks: list, tier: int) -> list:
    """Return only the chunks a given tier actually benefits from.

    Tier C (1, local ≤13B): 1 chunk max — qwen runs at ~15 tok/s on CPU,
    extra chunks cause 180s timeouts without improving quality.
    Tier B (2, 70B cloud): apply has_specific_data filter (same as Tier A)
    but keep up to 3 results — 70B models know general domain knowledge,
    only inject chunks with specific/numerical data they may not have.
    Tier A (3, frontier): only chunks with specific/numerical data — skip
    generic definitions the model already knows.
    """
    if tier == 1:
        return chunks[:1]
    if tier == 2:
        if chunks and isinstance(chunks[0], dict):
            filtered = [c for c in chunks if has_specific_data(c.get("text", ""))]
        else:
            filtered = [c for c in chunks if has_specific_data(str(c))]
        return filtered[:3]
    # Tier A — filter to chunks containing specific data
    if chunks and isinstance(chunks[0], dict):
        filtered = [c for c in chunks if has_specific_data(c.get("text", ""))]
    else:
        filtered = [c for c in chunks if has_specific_data(str(c))]
    return filtered


# ── Intent-specific suffixes ─────────────────────────────────────────────────

INTENT_SUFFIXES: dict[str, str] = {
    "calculate": "\nShow each calculation step. State the final answer.",
    "explain": "\nStart with a one-sentence summary, then explain in detail.",
    "compare": "\nUse a structured comparison with consistent criteria.",
    "create": "\nOutline your approach briefly, then produce the deliverable.",
    "debug": "\n1. Identify the error 2. Root cause 3. Fix 4. Verify.",
    "review": "\nClassify issues as CRITICAL or SUGGESTION with location.",
}


# ── CoT detection ─────────────────────────────────────────────────────────────

_COT_SIGNALS = frozenset(
    [
        "derive",
        "derivation",
        "prove",
        "proof",
        "step by step",
        "step-by-step",
        "show your work",
        "how is",
        "why does",
        "explain how",
        "walk me through",
        "formula",
        "calculate",
        "computation",
        "algorithm for",
        "converge",
    ]
)


def _needs_cot(prompt: str) -> bool:
    """True if the prompt requires multi-step reasoning (derivation, proof, formula).

    Used to inject CoT instruction for Tier B even when intent pattern is 'explain'
    (e.g. "derive Black-Scholes" detects as 'explain', not 'calculate').
    Does NOT apply to Tier A — frontier models reason natively.
    """
    p = prompt.lower()
    return any(sig in p for sig in _COT_SIGNALS)


# ── Tier-specific prompt builders ────────────────────────────────────────────


def _build_prompt_tier_c(
    original: str, decomp: dict, domains: list, chunks: list, routing: dict
) -> str:
    """Tier C (local ≤13B): compact XML — 1 truncated chunk, CoT inside <task>.

    Budget: ~500 tokens total. qwen runs at ~15 tok/s on CPU; longer prompts
    cause 180s timeouts. No <instructions> tag — CoT inline keeps it tight.
    """
    parts = []
    if chunks:
        raw = chunks[0]["text"] if isinstance(chunks[0], dict) else str(chunks[0])
        truncated = raw[:200]
        parts.append(f"<context>\n{truncated}\n</context>")
    parts.append(f"<task>\n{original}\nThink step by step.\n</task>")
    return "\n\n".join(parts)


def _build_prompt_tier_b(
    original: str, decomp: dict, domains: list, chunks: list, routing: dict
) -> str:
    """Tier B (70B cloud): reference block + concise task.

    Adds CoT suffix when the query requires multi-step reasoning (formula derivation,
    proofs, step-by-step calculations) even if the intent pattern matched 'explain'.
    """
    parts = []
    if chunks:
        knowledge_block = "\n---\n".join(
            c["text"] if isinstance(c, dict) else str(c) for c in chunks
        )
        parts.append(f"<reference>\n{knowledge_block}\n</reference>")
    parts.append(original)
    prompt = "\n\n".join(parts)
    # CoT injection: for formula/derivation queries not caught by intent pattern
    if _needs_cot(original) and "step" not in prompt.lower():
        prompt += "\n\nThink step by step. Show your reasoning before giving the final answer."
    return prompt


def _build_prompt_tier_a(original: str, chunks: list) -> str:
    """Tier A (frontier): inject only specific data, no scaffolding or CoT."""
    if not chunks:
        return original
    knowledge_block = "\n---\n".join(
        c["text"] if isinstance(c, dict) else str(c) for c in chunks
    )
    if not knowledge_block.strip():
        return original
    return f"{knowledge_block}\n\n---\n\n{original}"


# ── Phase 5: Prompt construction ─────────────────────────────────────────────


def _build_amplified_prompt(
    original: str,
    decomp: dict,
    intent: dict,
    domains: list,
    chunks: list,
    routing: dict = None,
    tier: int = None,
) -> tuple[str, int]:
    """
    Constructs the amplified prompt, dispatching to a tier-specific builder
    when tier is provided. Tier C gets XML+CoT, Tier B gets a reference block,
    Tier A gets only specific/numerical data with no scaffolding.
    Falls back to the default [CONTEXT]/[KNOWLEDGE]/[REQUEST] format if tier is None.

    Returns:
        (amplified_prompt, chunks_injected) — post-filter count for accurate reporting.
    """
    if tier is not None and chunks:
        effective_chunks = filter_chunks_for_tier(chunks, tier)
    else:
        effective_chunks = chunks

    intent_action = decomp.get("action", "explain") if decomp else "explain"
    intent_suffix = INTENT_SUFFIXES.get(intent_action, "")

    if tier == 1:
        amplified = _build_prompt_tier_c(
            original, decomp, domains, effective_chunks, routing
        )
        if intent_suffix:
            # Replace generic CoT with intent-specific instruction to avoid duplication.
            if "Think step by step." in amplified:
                amplified = amplified.replace(
                    "Think step by step.", intent_suffix.strip()
                )
            else:
                amplified += intent_suffix
        return amplified, len(effective_chunks)
    if tier == 2:
        amplified = _build_prompt_tier_b(
            original, decomp, domains, effective_chunks, routing
        )
        if intent_suffix:
            amplified += intent_suffix
        return amplified, len(effective_chunks)
    if tier == 3:
        # Tier A: frontier models don't need structural instructions
        return _build_prompt_tier_a(original, effective_chunks), len(effective_chunks)

    # Default: original [CONTEXT]/[KNOWLEDGE]/[REQUEST] format (tier=None or unknown)
    chunks = effective_chunks
    parts = []

    # Context header
    ctx_lines = []
    if decomp["action"]:
        ctx_lines.append(f"Intent: {decomp['action'].upper()}")
    if decomp["entity"]:
        ctx_lines.append(f"Entity: {decomp['entity']}")
    if decomp["niche"]:
        ctx_lines.append(f"Domain niche: {decomp['niche']}")

    if routing and routing.get("active_centroids"):
        domain_lines = []
        for c in routing["active_centroids"]:
            agents_str = ", ".join(a["name"] for a in c.get("agents", []))
            label = c["domain"].replace("_", " ").title()
            domain_lines.append(f"- {label} ({c['weight']:.0%}): {agents_str}")
        ctx_lines.append(
            "Domain analysis (multi-centroid):\n" + "\n".join(domain_lines)
        )
    elif domains:
        top_domains = ", ".join(f"{d['domain']}({d['score']:.2f})" for d in domains[:2])
        ctx_lines.append(f"Relevant domains: {top_domains}")

    if ctx_lines:
        parts.append("[CONTEXT]\n" + "\n".join(ctx_lines))

    # Knowledge injection
    if chunks:
        if isinstance(chunks[0], str):
            knowledge_block = "\n---\n".join(chunks[:3])
        else:
            knowledge_block = str(chunks)
        parts.append(f"[KNOWLEDGE]\n{knowledge_block}")

    # Original request
    parts.append(f"[REQUEST]\n{original}")

    return "\n\n".join(parts), len(effective_chunks)


# ── Phase 6: Tier selection ───────────────────────────────────────────────────


# Niches that require precision over speed — always route to Tier A.
# These domains have high cost-of-error (wrong WACC, wrong drug dosage, wrong clause).
_HIGH_PRECISION_NICHES = {"finance", "trading", "legal", "medical", "regulatory"}


def _select_tier(intent: dict, domains: list[dict], decomp: dict) -> int:
    """
    Selects the minimum viable tier based on 3 signals (priority order):

    1. Niche (highest signal): precision niches always → Tier A.
       Rationale: finance/legal/medical have high cost-of-error. Wrong WACC or
       wrong drug dosage is worse than a slow response.
    2. Domain + intent (existing logic): broad domain escalation rules.
    3. Intent tier (fallback): intent's own tier estimate.
    """
    niche = decomp.get("niche", "")
    domain_names = {d["domain"] for d in domains}
    high_tier_domains = {"finance", "economics", "trading", "business"}
    high_tier_intents = {"forecast", "plan", "report"}
    mid_tier_intents = {"research", "compare", "analyze"}

    # Signal 1: precision niche → Tier A regardless of domain or intent
    if niche in _HIGH_PRECISION_NICHES:
        return 3

    # Signal 2: domain-based escalation (unchanged)
    if domain_names & high_tier_domains and intent["id"] in high_tier_intents:
        return 3
    if intent["id"] in high_tier_intents:
        return 3
    if intent["id"] in mid_tier_intents:
        return max(2, intent["tier"])

    # Signal 3: intent tier fallback
    return intent["tier"]


# ── Logging ───────────────────────────────────────────────────────────────────


def _log_amplification(
    original: str,
    amplified: str,
    decomp: dict,
    intent: dict,
    domains: list,
    tier: int,
    elapsed_ms: int,
    routing: dict = None,
):
    try:
        routing_method = "hierarchical_3level" if routing else "single"
        active_count = len(routing["active_centroids"]) if routing else 1
        queued_count = len(routing["queued_centroids"]) if routing else 0
        classification_ms = routing["classification_ms"] if routing else 0

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO amplification_log
                (created_at, original_prompt, amplified_prompt, action_detected, entity_detected,
                 niche_detected, intent_pattern, top_domain, tier_selected, elapsed_ms,
                 routing_method, active_centroids_count, queued_centroids_count, classification_ms)
                VALUES (datetime('now'),?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    original[:500],
                    amplified[:2000],
                    decomp["action"],
                    decomp["entity"],
                    decomp["niche"],
                    intent["id"],
                    domains[0]["domain"] if domains else "",
                    tier,
                    elapsed_ms,
                    routing_method,
                    active_count,
                    queued_count,
                    classification_ms,
                ),
            )
    except Exception:
        pass  # Non-critical: log failures don't block execution


# ── Main amplify function ─────────────────────────────────────────────────────


def amplify(
    prompt: str,
    agent_name: str = "",
    verbose: bool = False,
    domain: str = None,
    chunks: list = None,
) -> dict:
    """
    Amplifies a raw prompt through the 6-phase pipeline.

    Args:
        prompt:     Raw user prompt
        agent_name: Agent name for knowledge retrieval (e.g. 'finance-analyst')
        verbose:    Print pipeline stages to stderr

    Returns:
        {
          'original':  str,
          'amplified': str,
          'action':    str,
          'entity':    str,
          'niche':     str,
          'intent':    str,
          'domains':   list[dict],
          'tier':      int,
          'tier_label': str,
          'chunks_used': int,
        }
    """
    t0 = time.time()

    def _log(msg: str):
        if verbose:
            print(f"[amplifier] {msg}", file=sys.stderr)

    # Phase 1
    _log("phase 1: decompose")
    decomp = _decompose(prompt)

    # Phase 2
    routing = None
    if domain is not None:
        # Domain provided externally — skip scoring, no DB lookup needed
        domains = [{"domain": domain, "score": 1.0}]
        _log(f"phase 2: domain provided externally ({domain})")
    else:
        _log("phase 2: domain scoring (hierarchical)")
        try:
            from hierarchical_router import (
                classify_hierarchical_cached,
                retrieve_knowledge_by_routing,
            )

            routing = classify_hierarchical_cached(prompt)
            if routing["active_centroids"]:
                domains = [
                    {"domain": c["domain"], "score": c["weight"]}
                    for c in routing["active_centroids"]
                ]
                _log(
                    f"  hierarchical: {len(routing['active_centroids'])} active centroids"
                )
            else:
                domains = _score_domains(prompt)
                routing = None
        except ImportError:
            domains = _score_domains(prompt)
            routing = None

    # Phase 3
    _log("phase 3: intent match")
    intent = _match_intent(decomp["tokens"], prompt.lower())

    # Phase 4
    _log("phase 4: knowledge retrieval")
    if chunks is not None:
        # Chunks pre-retrieved from original prompt externally — normalize to list[str]
        if chunks and isinstance(chunks[0], dict):
            chunks = [c["text"] for c in chunks if c.get("text")]
        else:
            chunks = [str(c) for c in chunks if c]
        _log(f"  {len(chunks)} chunks provided externally")
    elif routing:
        try:
            from embeddings import get_embedding as _get_emb

            prompt_emb = _get_emb(prompt)
            knowledge_text = retrieve_knowledge_by_routing(routing, prompt_emb)
            chunks = [knowledge_text] if knowledge_text else []
            _log(f"  {len(chunks)} knowledge blocks from hierarchical routing")
        except Exception:
            chunks = []
    else:
        effective_agent = agent_name
        if not effective_agent and decomp["niche"]:
            niche_agent_map = {
                "finance": "finance-analyst",
                "trading": "finance-analyst",
                "video": "content-automator",
                "code": "python-specialist",
                "data": "data-analyst",
            }
            effective_agent = niche_agent_map.get(decomp["niche"], "")
        chunks = _retrieve_knowledge(effective_agent, prompt) if effective_agent else []
        _log(f"  {len(chunks)} chunks retrieved from '{effective_agent}'")

    # Phase 4.5: Template injection
    try:
        from template_loader import find_template_by_routing, format_template_for_prompt

        template = find_template_by_routing(routing) if routing else None
        template_text = format_template_for_prompt(template, prompt) if template else ""
    except ImportError:
        template_text = ""
    if template_text:
        chunks.append(template_text)

    # Phase 6 (moved before Phase 5 so tier is available for prompt construction)
    _log("phase 6: tier selection")
    tier = _select_tier(intent, domains, decomp)

    # Phase 4.6: Confidence gate — block chunks that would add noise
    # Tier C always enriches (Rule 1 in gate). Tier B/A filtered by threshold + specificity.
    if chunks and tier > 1:
        try:
            from confidence_gate import should_enrich

            top_domain = domains[0]["domain"] if domains else "unknown"
            # Normalize to list[dict] if chunks arrived as list[str]
            gate_chunks = (
                [{"text": c, "score": 0.5} for c in chunks]
                if chunks and isinstance(chunks[0], str)
                else chunks
            )
            if not should_enrich("", top_domain, gate_chunks, tier):
                _log(f"  gate: blocked {len(chunks)} chunks for Tier {tier}")
                chunks = []
        except ImportError:
            pass  # gate unavailable — proceed without filtering

    # Phase 5
    _log("phase 5: build prompt")
    amplified, chunks_injected = _build_amplified_prompt(
        prompt, decomp, intent, domains, chunks, routing, tier=tier
    )

    elapsed_ms = int((time.time() - t0) * 1000)
    _log(f"done in {elapsed_ms}ms → tier={tier} ({TIER_LABELS[tier]})")

    _log_amplification(
        prompt, amplified, decomp, intent, domains, tier, elapsed_ms, routing
    )

    return {
        "original": prompt,
        "amplified": amplified,
        "action": decomp["action"],
        "entity": decomp["entity"],
        "niche": decomp["niche"],
        "intent": intent["id"],
        "domains": domains,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "chunks_used": chunks_injected,  # post-filter: actual injected count
        "routing": routing,
    }


# ── CLI / test mode ───────────────────────────────────────────────────────────

_TEST_INPUTS = [
    "analiza el WACC de Apple y genera un reporte ejecutivo",
    "debug this Python function that crashes on empty input",
    "investiga las mejores estrategias de backtesting para BTC momentum",
    "crea un script para automatizar la generacion de reels con ElevenLabs",
    "explica la diferencia entre GARCH y EWMA para volatilidad",
    "optimiza este SQL query que tarda 10 segundos",
    "escribe el capitulo 3 de la novela, escena del cafe",
]


def _run_tests():
    print("[amplifier:TEST] Running 7 test inputs...\n")
    for i, prompt in enumerate(_TEST_INPUTS, 1):
        result = amplify(prompt, verbose=False)
        print(
            f"  [{i}] intent={result['intent']:10s} "
            f"tier={result['tier']} ({result['tier_label']:12s}) "
            f"chunks={result['chunks_used']} "
            f"niche={result['niche'] or '-':8s} "
            f"| {prompt[:60]}"
        )
    print("\n[amplifier:TEST] Done.")


def main():
    load_env()
    args = sys.argv[1:]

    if "--test" in args:
        _run_tests()
        return

    as_json = "--json" in args
    args = [a for a in args if not a.startswith("--")]

    if args:
        prompt = " ".join(args)
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        print(
            'Usage: python3 bin/intent_amplifier.py [--json] "<prompt>"',
            file=sys.stderr,
        )
        print("       python3 bin/intent_amplifier.py --test", file=sys.stderr)
        sys.exit(1)

    result = amplify(prompt, verbose=not as_json)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"\n[AMPLIFIER] Intent: {result['intent']} | Tier: {result['tier']} ({result['tier_label']})"
        )
        print(
            f"  Action={result['action']} Entity={result['entity']} Niche={result['niche']}"
        )
        if result["domains"]:
            print(f"  Domains: {result['domains'][:2]}")
        print(f"\n--- Amplified prompt ---\n{result['amplified']}\n")


if __name__ == "__main__":
    main()
