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
import sys
import time
from pathlib import Path
from typing import Optional

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
for _d in [JARVIS / "bin" / s for s in ["", "core", "agents", "monitoring", "tools", "ui"]]:
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
    {"id": "analyze",       "keywords": ["analiza", "analyze", "review", "evalua", "assess"],        "tier": 2},
    {"id": "generate",      "keywords": ["genera", "generate", "crea", "create", "produce", "write"],"tier": 1},
    {"id": "optimize",      "keywords": ["optimiza", "optimize", "mejora", "improve", "refactor"],   "tier": 1},
    {"id": "debug",         "keywords": ["debug", "fix", "corrige", "error", "falla", "bug"],        "tier": 1},
    {"id": "research",      "keywords": ["investiga", "research", "busca", "find", "discover"],      "tier": 2},
    {"id": "summarize",     "keywords": ["resume", "summarize", "condensa", "sintetiza", "brief"],   "tier": 1},
    {"id": "compare",       "keywords": ["compara", "compare", "diferencia", "vs", "versus"],        "tier": 2},
    {"id": "forecast",      "keywords": ["predice", "forecast", "proyecta", "project", "estima"],    "tier": 3},
    {"id": "explain",       "keywords": ["explica", "explain", "describe", "clarifica", "define"],   "tier": 1},
    {"id": "transform",     "keywords": ["convierte", "transform", "traduce", "translate", "migra"], "tier": 1},
    {"id": "validate",      "keywords": ["valida", "validate", "verifica", "verify", "check"],       "tier": 1},
    {"id": "plan",          "keywords": ["planifica", "plan", "diseña", "design", "architect"],      "tier": 3},
    {"id": "automate",      "keywords": ["automatiza", "automate", "pipeline", "schedule", "cron"],  "tier": 1},
    {"id": "report",        "keywords": ["reporte", "report", "informe", "dashboard", "executive"],  "tier": 3},
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
            if kw in tokens or any(t.startswith(kw[:5]) for t in tokens if len(kw) >= 5):
                action = pattern["id"]
                break
        if action:
            break

    # Entity: first capitalized word or noun-like token (heuristic)
    entity = ""
    for tok in prompt.split():
        if tok[0].isupper() and len(tok) > 2 and tok.lower() not in {
            "el", "la", "los", "las", "un", "una", "the", "a", "an",
        }:
            entity = tok
            break

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
        if any(s in lowered for s in signals):
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
            1 for kw in pattern["keywords"]
            if kw in prompt_lower or any(t.startswith(kw[:5]) for t in tokens if len(kw) >= 5)
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


# ── Phase 5: Prompt construction ─────────────────────────────────────────────


def _build_amplified_prompt(
    original: str,
    decomp: dict,
    intent: dict,
    domains: list,
    chunks: list,
    routing: dict = None,
) -> str:
    """
    Constructs the amplified prompt by injecting context layers.
    When routing is provided, shows multi-centroid domain analysis.
    """
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
        ctx_lines.append("Domain analysis (multi-centroid):\n" + "\n".join(domain_lines))
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

    return "\n\n".join(parts)


# ── Phase 6: Tier selection ───────────────────────────────────────────────────


def _select_tier(intent: dict, domains: list[dict], decomp: dict) -> int:
    """
    Selects the minimum viable tier based on intent and domain signals.
    Rules:
    - finance/trading domain + forecast/plan/report intent → tier 3
    - research/compare/analyze intent → tier 2
    - everything else → tier 1
    """
    domain_names = {d["domain"] for d in domains}
    high_tier_domains = {"finance", "economics", "trading", "business"}
    high_tier_intents = {"forecast", "plan", "report"}
    mid_tier_intents = {"research", "compare", "analyze"}

    if domain_names & high_tier_domains and intent["id"] in high_tier_intents:
        return 3
    if intent["id"] in high_tier_intents:
        return 3
    if intent["id"] in mid_tier_intents:
        return max(2, intent["tier"])
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
            conn.execute("""
                INSERT INTO amplification_log
                (created_at, original_prompt, amplified_prompt, action_detected, entity_detected,
                 niche_detected, intent_pattern, top_domain, tier_selected, elapsed_ms,
                 routing_method, active_centroids_count, queued_centroids_count, classification_ms)
                VALUES (datetime('now'),?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
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
            ))
    except Exception:
        pass  # Non-critical: log failures don't block execution


# ── Main amplify function ─────────────────────────────────────────────────────


def amplify(
    prompt: str,
    agent_name: str = "",
    verbose: bool = False,
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
    _log("phase 2: domain scoring (hierarchical)")
    routing = None
    try:
        from hierarchical_router import classify_hierarchical_cached, retrieve_knowledge_by_routing
        routing = classify_hierarchical_cached(prompt)
        if routing["active_centroids"]:
            primary = routing["active_centroids"][0]
            domains = [
                {"domain": c["domain"], "score": c["weight"]}
                for c in routing["active_centroids"]
            ]
            _log(f"  hierarchical: {len(routing['active_centroids'])} active centroids")
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
    if routing:
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
                "video":   "content-automator",
                "code":    "python-specialist",
                "data":    "data-analyst",
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

    # Phase 5
    _log("phase 5: build prompt")
    amplified = _build_amplified_prompt(prompt, decomp, intent, domains, chunks, routing)

    # Phase 6
    _log("phase 6: tier selection")
    tier = _select_tier(intent, domains, decomp)

    elapsed_ms = int((time.time() - t0) * 1000)
    _log(f"done in {elapsed_ms}ms → tier={tier} ({TIER_LABELS[tier]})")

    _log_amplification(prompt, amplified, decomp, intent, domains, tier, elapsed_ms, routing)

    return {
        "original":    prompt,
        "amplified":   amplified,
        "action":      decomp["action"],
        "entity":      decomp["entity"],
        "niche":       decomp["niche"],
        "intent":      intent["id"],
        "domains":     domains,
        "tier":        tier,
        "tier_label":  TIER_LABELS[tier],
        "chunks_used": len(chunks),
        "routing":     routing,
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
        print('Usage: python3 bin/intent_amplifier.py [--json] "<prompt>"', file=sys.stderr)
        print('       python3 bin/intent_amplifier.py --test', file=sys.stderr)
        sys.exit(1)

    result = amplify(prompt, verbose=not as_json)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n[AMPLIFIER] Intent: {result['intent']} | Tier: {result['tier']} ({result['tier_label']})")
        print(f"  Action={result['action']} Entity={result['entity']} Niche={result['niche']}")
        if result["domains"]:
            print(f"  Domains: {result['domains'][:2]}")
        print(f"\n--- Amplified prompt ---\n{result['amplified']}\n")


if __name__ == "__main__":
    main()
