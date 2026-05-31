#!/usr/bin/env python3
"""
DQ Paper Harvester — Automatic knowledge base updater.

Searches for recent papers via free APIs (arXiv, Semantic Scholar),
summarizes them into structured knowledge files, and indexes them.

Usage:
    python3 bin/paper_harvester.py --domain social_sciences --agent finance
    python3 bin/paper_harvester.py --all
    python3 bin/paper_harvester.py --domain applied_sciences --query "LLM routing optimization"
"""

import os
import re
import sys
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import requests

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
sys.path.insert(0, str(JARVIS / "bin"))
KNOWLEDGE = JARVIS / "knowledge"

# Free API endpoints
ARXIV_API = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

# Domain → search queries mapping
DOMAIN_QUERIES = {
    "formal_sciences": {
        "mathematics": ["mathematical optimization 2025 2026", "linear algebra applications"],
        "statistics": ["bayesian inference methods 2025", "statistical learning theory"],
        "algorithms": ["algorithm efficiency optimization", "data structure novel approaches"],
    },
    "natural_sciences": {
        "physics": ["quantum computing applications 2025", "thermodynamics efficiency"],
        "chemistry": ["organic synthesis novel methods", "biochemistry protein"],
        "biology": ["gene therapy 2025 2026", "cell biology CRISPR"],
    },
    "social_sciences": {
        "economics": ["behavioral economics nudge theory", "macroeconomic policy AI"],
        "finance": ["portfolio optimization machine learning", "VaR estimation methods 2025"],
        "marketing": ["digital marketing AI automation", "SEO algorithm changes 2025"],
        "business": ["startup scaling strategies", "business model innovation"],
        "law": ["AI regulation compliance 2025", "contract automation"],
    },
    "humanities_arts": {
        "literature": ["narrative AI generation", "computational creativity"],
        "philosophy": ["AI ethics frameworks 2025", "machine consciousness debate"],
        "history": ["digital humanities methodology", "computational history"],
    },
    "applied_sciences": {
        "software_engineering": ["microservices architecture patterns", "CI/CD optimization"],
        "data_engineering": ["real-time data pipeline", "vector database comparison"],
        "web_development": ["frontend framework performance 2025", "web accessibility"],
        "ai_ml": ["LLM routing cost optimization", "prompt engineering techniques 2025"],
    },
}


def search_arxiv(query: str, max_results: int = 3) -> list:
    """Search arXiv for papers."""
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        resp = requests.get(ARXIV_API, params=params, timeout=15)
        resp.raise_for_status()
        entries = re.findall(r"<entry>(.*?)</entry>", resp.text, re.DOTALL)
        papers = []
        for entry in entries:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            published = re.search(r"<published>(.*?)</published>", entry)
            arxiv_id = re.search(r"<id>(.*?)</id>", entry)
            if title and summary:
                papers.append({
                    "title": title.group(1).strip().replace("\n", " "),
                    "abstract": summary.group(1).strip().replace("\n", " "),
                    "published": published.group(1)[:10] if published else "",
                    "source": arxiv_id.group(1) if arxiv_id else "",
                    "api": "arxiv",
                })
        return papers
    except Exception as e:
        print(f"  [warn] arXiv search failed: {e}")
        return []


def search_semantic_scholar(query: str, max_results: int = 3) -> list:
    """Search Semantic Scholar for papers."""
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,citationCount,url",
        "year": "2024-2026",
    }
    try:
        resp = requests.get(SEMANTIC_SCHOLAR_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        papers = []
        for p in data.get("data", []):
            if p.get("abstract"):
                papers.append({
                    "title": p["title"],
                    "abstract": p["abstract"],
                    "published": str(p.get("year", "")),
                    "citations": p.get("citationCount", 0),
                    "source": p.get("url", ""),
                    "api": "semantic_scholar",
                })
        return papers
    except Exception as e:
        print(f"  [warn] Semantic Scholar search failed: {e}")
        return []


def summarize_paper_to_knowledge(paper: dict, domain: str, agent: str) -> str:
    """Convert a paper into a structured knowledge file content."""
    title = paper["title"]
    abstract = paper["abstract"]

    # Extract potential equations (patterns like x = ..., f(x), etc.)
    equations = re.findall(r"[A-Za-z]\s*[=\u2248\u2264\u2265<>]\s*[^,;.]{3,30}", abstract)

    content = f"""# {title}

## Source
- Published: {paper.get('published', 'Unknown')}
- API: {paper.get('api', 'Unknown')}
- URL: {paper.get('source', 'N/A')}
- Retrieved: {datetime.utcnow().strftime('%Y-%m-%d')}

## Core Insight
{abstract[:500]}

## Key Concepts
"""
    # Extract key technical terms (capitalized multi-word phrases)
    terms = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", abstract)
    unique_terms = list(dict.fromkeys(terms))[:8]
    for term in unique_terms:
        content += f"- **{term}**\n"

    if equations:
        content += "\n## Equations/Formulas Referenced\n"
        for eq in equations[:5]:
            content += f"- `{eq.strip()}`\n"

    content += f"""
## Practical Application
This research is relevant to {domain.replace('_', ' ')} / {agent.replace('_', ' ')}.
Key takeaway: {abstract[:200]}

## Domain Tags
- Centroid: {domain}
- Agent: {agent}
- Auto-harvested: true
"""
    return content


def harvest_domain(domain: str, agent: str = None, max_papers: int = 3) -> int:
    """Harvest papers for a domain/agent and create knowledge files."""
    domain_queries = DOMAIN_QUERIES.get(domain, {})

    if agent:
        agents_to_process = {agent: domain_queries.get(agent, [])}
    else:
        agents_to_process = domain_queries

    total_files = 0

    for ag, queries in agents_to_process.items():
        print(f"\n  Harvesting {domain}/{ag}...")

        for query in queries:
            papers = search_arxiv(query, max_results=2)
            papers += search_semantic_scholar(query, max_results=1)

            for paper in papers:
                safe_title = re.sub(r"[^a-z0-9]+", "_", paper["title"].lower())[:60]
                filename = f"paper_{safe_title}.md"

                out_dir = KNOWLEDGE / domain / ag / "papers"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / filename

                if out_path.exists():
                    print(f"    [skip] {filename} (already exists)")
                    continue

                content = summarize_paper_to_knowledge(paper, domain, ag)
                out_path.write_text(content, encoding="utf-8")
                print(f"    [new] {filename}")
                total_files += 1

            # Rate limit: 1 second between API calls
            time.sleep(1)

    if total_files > 0:
        print(f"\n  Reindexing {domain}...")
        subprocess.run(
            ["python3", str(JARVIS / "bin" / "knowledge_indexer.py"), "--domain", domain],
            capture_output=True,
        )

    print(f"\n  {total_files} new paper(s) added to {domain}")
    return total_files


def harvest_all(max_papers_per_query: int = 2) -> int:
    """Harvest papers for all domains."""
    total = 0
    for domain in DOMAIN_QUERIES:
        total += harvest_domain(domain, max_papers=max_papers_per_query)
    print(f"\n{'=' * 50}")
    print(f"Total: {total} new papers harvested across all domains")
    return total


def prune_outdated(domain: str, max_age_days: int = 180) -> int:
    """Remove paper knowledge files older than max_age_days."""
    papers_dir = KNOWLEDGE / domain
    pruned = 0
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    for paper_file in papers_dir.rglob("papers/paper_*.md"):
        content = paper_file.read_text(errors="ignore")
        match = re.search(r"Retrieved: (\d{4}-\d{2}-\d{2})", content)
        if match:
            retrieved = datetime.strptime(match.group(1), "%Y-%m-%d")
            if retrieved < cutoff:
                paper_file.unlink()
                pruned += 1
                print(f"  [pruned] {paper_file.name} (retrieved {match.group(1)})")

    if pruned > 0:
        print(f"  Pruned {pruned} outdated papers from {domain}")
    return pruned


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DQ Paper Harvester")
    parser.add_argument("--domain", help="Specific domain to harvest")
    parser.add_argument("--agent", help="Specific agent within domain")
    parser.add_argument("--query", help="Custom search query (used with --domain + --agent)")
    parser.add_argument("--all", action="store_true", help="Harvest all domains")
    parser.add_argument("--prune", action="store_true", help="Remove outdated papers")
    parser.add_argument("--prune-days", type=int, default=180, help="Max age in days (default: 180)")
    args = parser.parse_args()

    if args.prune:
        domains = [args.domain] if args.domain else list(DOMAIN_QUERIES.keys())
        for d in domains:
            prune_outdated(d, args.prune_days)
    elif getattr(args, "all"):
        harvest_all()
    elif args.domain:
        if args.query and args.agent:
            # Inject custom query into the domain map for this run
            papers = search_arxiv(args.query, max_results=3)
            papers += search_semantic_scholar(args.query, max_results=2)
            ag = args.agent
            out_dir = KNOWLEDGE / args.domain / ag / "papers"
            out_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for paper in papers:
                safe_title = re.sub(r"[^a-z0-9]+", "_", paper["title"].lower())[:60]
                out_path = out_dir / f"paper_{safe_title}.md"
                if not out_path.exists():
                    out_path.write_text(
                        summarize_paper_to_knowledge(paper, args.domain, ag),
                        encoding="utf-8",
                    )
                    print(f"  [new] {out_path.name}")
                    count += 1
            print(f"\n  {count} paper(s) saved. Run knowledge_indexer.py --domain {args.domain} to reindex.")
        else:
            harvest_domain(args.domain, args.agent)
    else:
        parser.print_help()
