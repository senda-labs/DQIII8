#!/usr/bin/env python3
"""
JARVIS — Auto Researcher
Scrapes arxiv, GitHub trending, Anthropic news, and HuggingFace papers.
Scores each item and queues high-value items for sandbox testing.

Usage:
    python3 bin/auto_researcher.py           # arxiv only (fast)
    python3 bin/auto_researcher.py --full    # all sources
    python3 bin/auto_researcher.py --dry-run # print without inserting
"""

import argparse
import html
import os
import re
import sqlite3
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"
QUEUE_DIR = JARVIS_ROOT / "tasks" / "research_queue"

KEYWORDS = [
    "agent",
    "memory",
    "llm",
    "autonomous",
    "orchestrat",
    "embedding",
    "retrieval",
    "multiagent",
    "workflow",
    "tool use",
    "claude",
    "openai",
    "anthropic",
    "langchain",
    "langgraph",
]

SCORE_TITLE = 3
SCORE_DESC = 1
SCORE_STARS = 2
SCORE_ANTHROPIC = 5
SCORE_PYTHON = 2
MIN_SCORE = 5


def _score_item(title: str, description: str, stars: int = 0, source: str = "") -> float:
    score = 0.0
    t = title.lower()
    d = description.lower()
    for kw in KEYWORDS:
        if kw in t:
            score += SCORE_TITLE
        elif kw in d:
            score += SCORE_DESC
    if stars > 1000:
        score += SCORE_STARS
    if "anthropic" in source.lower() or "anthropic" in t:
        score += SCORE_ANTHROPIC
    if "python" in t or "python" in d:
        score += SCORE_PYTHON
    return score


def _fetch_url(url: str, timeout: int = 15) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (JARVIS/1.0 Research Bot)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[auto_researcher] fetch error {url}: {e}", file=sys.stderr)
        return ""


def fetch_arxiv() -> list[dict]:
    """Fetch AI agent / memory papers from arxiv Atom API."""
    url = (
        "https://export.arxiv.org/api/query?"
        "search_query=ti:AI+agent+memory+OR+ti:LLM+autonomous+OR+ti:multi+agent&"
        "max_results=20&sortBy=submittedDate&sortOrder=descending"
    )
    raw = _fetch_url(url)
    if not raw:
        return []

    items = []
    try:
        root = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("a:summary", "", ns) or "").strip()[:300]
            link_el = entry.find("a:link[@rel='alternate']", ns)
            url_item = link_el.attrib.get("href", "") if link_el is not None else ""
            if not url_item:
                id_el = entry.findtext("a:id", "", ns)
                url_item = id_el.strip() if id_el else ""
            score = _score_item(title, summary, source="arxiv")
            if score >= MIN_SCORE:
                items.append(
                    {
                        "source": "arxiv",
                        "title": title,
                        "url": url_item,
                        "summary": summary,
                        "score": score,
                    }
                )
    except Exception as e:
        print(f"[auto_researcher] arxiv parse error: {e}", file=sys.stderr)

    return items


def fetch_github_trending() -> list[dict]:
    """Scrape GitHub trending Python repos (weekly)."""
    raw = _fetch_url("https://github.com/trending/python?since=weekly")
    if not raw:
        return []

    items = []
    # Match repo article blocks
    repos = re.findall(
        r'<h2[^>]*class="h3 lh-condensed"[^>]*>\s*<a href="/([^"]+)"',
        raw,
    )
    descriptions = re.findall(
        r'<p[^>]*class="col-9[^"]*"[^>]*>\s*(.*?)\s*</p>',
        raw,
        re.DOTALL,
    )
    stars_list = re.findall(
        r'<a[^>]*href="[^"]+/stargazers"[^>]*>\s*([\d,]+)\s*</a>',
        raw,
    )

    for i, repo_path in enumerate(repos[:20]):
        desc = descriptions[i].strip() if i < len(descriptions) else ""
        desc = re.sub(r"<[^>]+>", "", desc).strip()
        desc = html.unescape(desc)
        stars_str = stars_list[i].replace(",", "") if i < len(stars_list) else "0"
        try:
            stars = int(stars_str)
        except ValueError:
            stars = 0
        title = repo_path.replace("/", " / ")
        score = _score_item(title, desc, stars=stars, source="github")
        if score >= MIN_SCORE:
            items.append(
                {
                    "source": "github-trending",
                    "title": title,
                    "url": f"https://github.com/{repo_path}",
                    "summary": desc[:300],
                    "score": score,
                }
            )

    return items


def fetch_anthropic_news() -> list[dict]:
    """Scrape Anthropic news page for recent posts."""
    raw = _fetch_url("https://www.anthropic.com/news")
    if not raw:
        return []

    items = []
    # Extract h2/h3 titles and nearby href links
    blocks = re.findall(
        r"<(?:h2|h3)[^>]*>(.*?)</(?:h2|h3)>",
        raw,
        re.DOTALL,
    )
    hrefs = re.findall(r'href="(/news/[^"]+)"', raw)

    seen_titles: set[str] = set()
    for i, block in enumerate(blocks[:15]):
        title = re.sub(r"<[^>]+>", "", block).strip()
        title = html.unescape(title)
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        url_item = (
            f"https://www.anthropic.com{hrefs[i]}"
            if i < len(hrefs)
            else "https://www.anthropic.com/news"
        )
        score = _score_item(title, "", source="anthropic")
        if score >= MIN_SCORE:
            items.append(
                {
                    "source": "anthropic-news",
                    "title": title,
                    "url": url_item,
                    "summary": title,
                    "score": score,
                }
            )

    return items


def fetch_huggingface_papers() -> list[dict]:
    """Scrape HuggingFace papers page."""
    raw = _fetch_url("https://huggingface.co/papers")
    if not raw:
        return []

    items = []
    # Find paper titles in h3 tags
    titles = re.findall(
        r'<h3[^>]*class="[^"]*mb-1[^"]*"[^>]*>\s*<a href="(/papers/[^"]+)"[^>]*>(.*?)</a>',
        raw,
        re.DOTALL,
    )
    if not titles:
        # fallback
        titles = re.findall(r'href="(/papers/\d{4}\.\d+)"[^>]*>(.*?)</a>', raw, re.DOTALL)

    for href, title_raw in titles[:15]:
        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        title = html.unescape(title)
        if not title:
            continue
        score = _score_item(title, "", source="huggingface")
        if score >= MIN_SCORE:
            items.append(
                {
                    "source": "huggingface-papers",
                    "title": title,
                    "url": f"https://huggingface.co{href}",
                    "summary": title,
                    "score": score,
                }
            )

    return items


def insert_items(items: list[dict], dry_run: bool, session_id: str = "auto_researcher") -> int:
    """Insert items into research_items + write queue files."""
    if dry_run:
        for item in items:
            print(f"  [{item['score']:.0f}] [{item['source']}] {item['title'][:80]}")
        return len(items)

    if not DB.exists():
        print("[auto_researcher] DB not found — skipping insert")
        return 0

    QUEUE_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB), timeout=5)
    inserted = 0
    now = datetime.now()

    for item in items:
        # Check for duplicate title (skip if already queued)
        exists = conn.execute(
            "SELECT COUNT(*) FROM research_items WHERE title=?", (item["title"],)
        ).fetchone()[0]
        if exists:
            continue

        conn.execute(
            "INSERT INTO research_items (source, title, url, summary, score, status, session_id) "
            "VALUES (?, ?, ?, ?, ?, 'PENDIENTE_TEST', ?)",
            (
                item["source"],
                item["title"],
                item["url"],
                item["summary"],
                item["score"],
                session_id,
            ),
        )
        inserted += 1

        # Write queue file
        ts = now.strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", item["title"].lower())[:40]
        qfile = QUEUE_DIR / f"{ts}-{slug}.md"
        qfile.write_text(
            f"# {item['title']}\n\n"
            f"Source: {item['source']}\n"
            f"URL: {item['url']}\n"
            f"Score: {item['score']}\n"
            f"Status: PENDIENTE_TEST\n\n"
            f"## Summary\n{item['summary']}\n",
            encoding="utf-8",
        )

    conn.commit()
    conn.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS auto researcher")
    parser.add_argument(
        "--full", action="store_true", help="Fetch all sources (default: arxiv only)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print results without inserting")
    args = parser.parse_args()

    all_items: list[dict] = []

    print("[auto_researcher] Fetching arxiv...")
    all_items.extend(fetch_arxiv())

    if args.full:
        print("[auto_researcher] Fetching GitHub trending...")
        all_items.extend(fetch_github_trending())
        print("[auto_researcher] Fetching Anthropic news...")
        all_items.extend(fetch_anthropic_news())
        print("[auto_researcher] Fetching HuggingFace papers...")
        all_items.extend(fetch_huggingface_papers())

    # Sort by score descending
    all_items.sort(key=lambda x: x["score"], reverse=True)

    print(f"[auto_researcher] Found {len(all_items)} qualifying items (score >= {MIN_SCORE})")

    if args.dry_run:
        print("\n--- Dry run results ---")
        insert_items(all_items, dry_run=True)
        print(f"\n[auto_researcher] Would insert {len(all_items)} items.")
    else:
        inserted = insert_items(all_items, dry_run=False)
        print(f"[auto_researcher] Inserted {inserted} new items into research_items.")


if __name__ == "__main__":
    main()
