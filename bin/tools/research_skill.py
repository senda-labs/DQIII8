#!/usr/bin/env python3
"""
DQIII8 Research Skill
=====================
Importable API over paper_harvester.py for autonomous knowledge base improvement.
Searches for papers, verifies claims against evidence, updates knowledge files,
and measures the impact on the domain index.

Functions:
    research(topic, domain)              -> list[dict] of papers
    verify_claim(claim, domain)          -> dict with status/confidence
    update_knowledge(papers, domain)     -> int (new chunks added)
    measure_impact(domain, before_count) -> dict

Usage:
    from research_skill import research, update_knowledge, measure_impact
    papers = research("RAG prompt optimization", "applied_sciences")
    before = sum(len(...) for domain index)
    added = update_knowledge(papers, "applied_sciences")
    print(measure_impact("applied_sciences", before))

CLI:
    python3 bin/tools/research_skill.py research "RAG prompt optimization" applied_sciences
    python3 bin/tools/research_skill.py verify "RAG improves GPT-4 by 10%" applied_sciences
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

JARVIS = Path(__file__).resolve().parent.parent.parent
for _d in [JARVIS / "bin" / s for s in ["", "core", "agents", "monitoring", "tools", "ui"]]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from paper_harvester import (
    KNOWLEDGE,
    search_arxiv,
    search_semantic_scholar,
    summarize_paper_to_knowledge,
)


# ── Core functions ────────────────────────────────────────────────────────────


def research(topic: str, domain: str, max_results: int = 5) -> list[dict]:
    """Search arXiv + Semantic Scholar for papers on a topic.

    Returns deduplicated list of dicts:
        {"title": str, "abstract": str, "source": str, "published": str, "api": str}
    Only papers from the last ~12 months are returned by default (sortBy=submittedDate).
    """
    papers = search_arxiv(topic, max_results=max_results)
    papers += search_semantic_scholar(topic, max_results=max_results)

    # Deduplicate by normalised title prefix
    seen: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        key = re.sub(r"\s+", " ", p["title"].lower().strip())[:60]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def verify_claim(claim: str, domain: str) -> dict:
    """Search for papers that support or contradict a claim.

    Returns:
        {
            "claim": str,
            "status": "VERIFIED" | "PARTIALLY" | "UNVERIFIED",
            "sources": list[{"title": str, "url": str}],
            "confidence": float,
        }

    Status thresholds:
        VERIFIED   — 2+ papers with significant keyword overlap
        PARTIALLY  — exactly 1 supporting paper
        UNVERIFIED — 0 papers found or no overlap
    """
    # Extract meaningful keywords (len > 4 avoids noise like "that", "with")
    keywords = [w for w in re.findall(r"[a-z]+", claim.lower()) if len(w) > 4]
    query = " ".join(keywords[:6])
    papers = research(query, domain, max_results=6)

    claim_words = set(keywords)
    supporting: list[dict] = []
    for p in papers:
        abstract_words = set(re.findall(r"[a-z]+", p.get("abstract", "").lower()))
        overlap = len(claim_words & abstract_words)
        if overlap >= 2:
            supporting.append(p)

    if len(supporting) >= 2:
        status, confidence = "VERIFIED", 0.8
    elif len(supporting) == 1:
        status, confidence = "PARTIALLY", 0.5
    else:
        status, confidence = "UNVERIFIED", 0.1

    return {
        "claim": claim,
        "status": status,
        "sources": [
            {"title": p["title"], "url": p.get("source", "")}
            for p in supporting
        ],
        "confidence": confidence,
    }


def update_knowledge(papers: list[dict], domain: str, agent: str = "research") -> int:
    """Convert a paper list to knowledge files and re-index the domain.

    Skips papers whose file already exists (idempotent).
    Re-runs knowledge_indexer after adding new files.
    Returns the number of new files written.
    """
    out_dir = KNOWLEDGE / domain / agent / "papers"
    out_dir.mkdir(parents=True, exist_ok=True)

    added = 0
    for paper in papers:
        safe = re.sub(r"[^a-z0-9]+", "_", paper["title"].lower())[:60]
        out_path = out_dir / f"paper_{safe}.md"
        if out_path.exists():
            continue
        content = summarize_paper_to_knowledge(paper, domain, agent)
        out_path.write_text(content, encoding="utf-8")
        added += 1

    if added > 0:
        indexer = JARVIS / "bin" / "knowledge_indexer.py"
        subprocess.run(
            ["python3", str(indexer), "--domain", domain],
            capture_output=True,
        )

    return added


def measure_impact(domain: str, before_chunks: int) -> dict:
    """Compare domain knowledge chunk count before and after an update.

    Args:
        domain:        Domain folder name (e.g. "applied_sciences")
        before_chunks: Chunk count before update (from a previous call or 0)

    Returns:
        {"before": int, "after": int, "delta": int, "improved": bool}
    """
    index_paths = list((KNOWLEDGE / domain).rglob("index.json"))
    after_chunks = 0
    for p in index_paths:
        try:
            after_chunks += len(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    delta = after_chunks - before_chunks
    return {
        "before": before_chunks,
        "after": after_chunks,
        "delta": delta,
        "improved": delta > 0,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DQIII8 Research Skill")
    sub = parser.add_subparsers(dest="cmd")

    p_res = sub.add_parser("research", help="Search papers on a topic")
    p_res.add_argument("topic", help="Search topic")
    p_res.add_argument("domain", help="Domain (e.g. applied_sciences)")
    p_res.add_argument("--max", type=int, default=5, dest="max_results")

    p_ver = sub.add_parser("verify", help="Verify a claim against papers")
    p_ver.add_argument("claim", help="Claim to verify")
    p_ver.add_argument("domain", help="Domain to search")

    p_upd = sub.add_parser("update", help="Update knowledge from a topic search")
    p_upd.add_argument("topic")
    p_upd.add_argument("domain")
    p_upd.add_argument("--agent", default="research")
    p_upd.add_argument("--max", type=int, default=5, dest="max_results")

    args = parser.parse_args()

    if args.cmd == "research":
        papers = research(args.topic, args.domain, args.max_results)
        print(f"Found {len(papers)} papers:")
        for p in papers:
            print(f"  [{p.get('api','?')}] {p['title'][:80]}")

    elif args.cmd == "verify":
        result = verify_claim(args.claim, args.domain)
        print(f"Status: {result['status']} (confidence={result['confidence']:.1f})")
        for s in result["sources"]:
            print(f"  - {s['title'][:70]}")

    elif args.cmd == "update":
        papers = research(args.topic, args.domain, args.max_results)
        added = update_knowledge(papers, args.domain, args.agent)
        print(f"Added {added} new knowledge files to {args.domain}/{args.agent}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
