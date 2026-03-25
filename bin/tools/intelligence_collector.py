#!/usr/bin/env python3
"""DQIII8 Intelligence Collector — automated knowledge gathering.

Collects news, updates, and papers from configured sources.
Classifies relevance using Groq ($0).
Generates daily digest for Telegram.

Fetch methods:
    rss          — feedparser (primary, free, instant)
    reddit_json  — Reddit JSON API (free, no auth)
    web_firecrawl — Firecrawl API (500 free credits, requires FIRECRAWL_API_KEY)

Usage:
    python3 bin/tools/intelligence_collector.py --collect --tier 1
    python3 bin/tools/intelligence_collector.py --collect --tier 2,3
    python3 bin/tools/intelligence_collector.py --digest
    python3 bin/tools/intelligence_collector.py --status
"""

import argparse
import json
import os
import sqlite3
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

import feedparser

import logging
log = logging.getLogger(__name__)
DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = DQIII8_ROOT / "database" / "jarvis_metrics.db"
SOURCES_PATH = DQIII8_ROOT / "config" / "intelligence_sources.json"


# ---------------------------------------------------------------------------
# Config & DB
# ---------------------------------------------------------------------------


def load_sources(tiers=None):
    """Load intelligence sources, optionally filtered by tier."""
    with open(SOURCES_PATH, encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    if tiers:
        tier_list = [int(t) for t in str(tiers).split(",")]
        sources = [s for s in sources if s["tier"] in tier_list]
    return sources


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Fetch methods
# ---------------------------------------------------------------------------


def fetch_rss(url, max_items=10):
    """Fetch and parse RSS/Atom feed via feedparser."""
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append(
                {
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[:500],
                    "published": entry.get("published", ""),
                }
            )
        return items
    except Exception as e:
        print(f"  RSS error: {e}")
        return []


def fetch_reddit_json(url, max_items=10):
    """Fetch Reddit hot posts as JSON (score > 50 filter)."""
    try:
        # Ensure .json suffix and limit param
        json_url = url.rstrip("/")
        if not json_url.endswith(".json"):
            json_url += ".json"
        json_url += "?limit=25"
        req = urllib.request.Request(json_url, headers={"User-Agent": "DQIII8/1.0"})
        response = urllib.request.urlopen(req, timeout=15)
        data = json.loads(response.read())
        items = []
        for post in data.get("data", {}).get("children", [])[:max_items]:
            d = post.get("data", {})
            if d.get("score", 0) > 50:
                items.append(
                    {
                        "title": d.get("title", ""),
                        "url": f"https://reddit.com{d.get('permalink', '')}",
                        "summary": d.get("selftext", "")[:500],
                        "score": d.get("score", 0),
                    }
                )
        return items
    except Exception as e:
        print(f"  Reddit error: {e}")
        return []


def fetch_firecrawl(url):
    """Scrape web page via Firecrawl REST API (requires FIRECRAWL_API_KEY)."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        print("  Firecrawl: no API key, skipping")
        return ""
    try:
        req_url = "https://api.firecrawl.dev/v1/scrape"
        data = json.dumps({"url": url, "formats": ["markdown"]}).encode()
        req = urllib.request.Request(
            req_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        response = urllib.request.urlopen(req, timeout=30)
        result = json.loads(response.read())
        return result.get("data", {}).get("markdown", "")[:5000]
    except Exception as e:
        print(f"  Firecrawl error: {e}")
        return ""


def scrape_source(source):
    """Fetch items using the best method for this source type."""
    source_type = source.get("type", "rss")

    if source_type == "rss":
        return fetch_rss(source["rss"])

    if source_type == "reddit_json":
        return fetch_reddit_json(source["rss"])

    if source_type == "web_firecrawl":
        content = fetch_firecrawl(source["url"])
        if content:
            return extract_items_from_content(content, source)
        return []

    # Fallback: try RSS key, then give up
    if source.get("rss"):
        return fetch_rss(source["rss"])
    return []


# ---------------------------------------------------------------------------
# Classification (Groq — $0)
# ---------------------------------------------------------------------------


def extract_items_from_content(content, source):
    """Use Groq to extract news items from raw markdown/HTML content."""
    prompt = (
        f"Extract the 5 most recent news items from this content.\n"
        f"Source: {source['name']} ({source.get('url', '')})\n"
        f"Keywords to look for: {', '.join(source.get('keywords', []))}\n\n"
        f"Content (first 3000 chars):\n{content[:3000]}\n\n"
        f"Respond ONLY with JSON array, no text before or after:\n"
        f'[{{"title": "...", "summary": "...", "url": "..."}}]\n'
        f"If no relevant items found, respond: []"
    )
    try:
        result = subprocess.run(
            [
                "python3",
                str(DQIII8_ROOT / "bin" / "core" / "openrouter_wrapper.py"),
                "--agent",
                "research-analyst",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(DQIII8_ROOT),
        )
        text = result.stdout.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        print(f"  LLM extract error: {e}")
    return []


def keyword_filter(items, keywords):
    """Fast keyword pre-filter before LLM classification (saves Groq calls)."""
    if not keywords:
        return items
    filtered = []
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if any(kw.lower() in text for kw in keywords):
            filtered.append(item)
    return filtered


def classify_item(item, source):
    """Classify relevance using Groq (Tier B — free)."""
    prompt = (
        "Classify this AI news item for DQIII8 (AI orchestration system that routes "
        "prompts to cheapest capable model).\n"
        f"Title: {item.get('title', '')}\n"
        f"Summary: {item.get('summary', '')[:200]}\n"
        f"Source: {source['name']}\n\n"
        "Respond ONLY with JSON:\n"
        '{"relevance": "HIGH or MEDIUM or LOW or IGNORE", '
        '"action": "integrate or evaluate or monitor or ignore", '
        '"affects": "api or model or tool or knowledge or infrastructure or none"}'
    )
    try:
        result = subprocess.run(
            [
                "python3",
                str(DQIII8_ROOT / "bin" / "core" / "openrouter_wrapper.py"),
                "--agent",
                "research-analyst",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(DQIII8_ROOT),
        )
        text = result.stdout.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as _exc:
        log.warning('%s: %s', __name__, _exc)
    return {"relevance": "LOW", "action": "monitor", "affects": "none"}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def store_item(item, source, classification):
    """Store classified item in DB, skip duplicates by exact title."""
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM intelligence_items WHERE title = ?",
            (item.get("title", ""),),
        ).fetchone()
        if existing:
            return False

        conn.execute(
            """
            INSERT INTO intelligence_items
            (source, title, url, summary, relevance, action_type, affects)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source["name"],
                item.get("title", "Unknown"),
                item.get("url", source.get("url", "")),
                item.get("summary", ""),
                classification.get("relevance", "LOW"),
                classification.get("action", "monitor"),
                classification.get("affects", "none"),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"  DB error: {e}")
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main commands
# ---------------------------------------------------------------------------


def collect(tiers="1"):
    """Collect from all sources of specified tiers."""
    sources = load_sources(tiers)
    print(f"[INTEL] Collecting from {len(sources)} sources (tiers: {tiers})")

    total_new = 0
    for source in sources:
        print(f"  [{source['name']}]", end=" ", flush=True)

        items = scrape_source(source)
        if not items:
            print("no items")
            continue

        keywords = source.get("keywords", [])
        items = keyword_filter(items, keywords)
        print(f"{len(items)} relevant", end=" ", flush=True)

        stored_count = 0
        for item in items[:5]:
            classification = classify_item(item, source)
            if store_item(item, source, classification):
                total_new += 1
                stored_count += 1

        print(f"-> {stored_count} stored")

    print(f"[INTEL] Total new items: {total_new}")


def generate_digest():
    """Generate daily digest and optionally send via Telegram."""
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    items = conn.execute(
        """
        SELECT * FROM intelligence_items
        WHERE date(created_at) = ? AND notified = 0
        ORDER BY
            CASE relevance
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 4
            END
        """,
        (today,),
    ).fetchall()

    if not items:
        print("[INTEL] No new items for digest today")
        return

    lines = [f"DQ Intelligence Briefing - {today}\n"]

    high = [i for i in items if i["relevance"] == "HIGH"]
    medium = [i for i in items if i["relevance"] == "MEDIUM"]
    low = [i for i in items if i["relevance"] == "LOW"]

    if high:
        lines.append(f"URGENTE ({len(high)})")
        for idx, item in enumerate(high, 1):
            lines.append(f"{idx}. {item['title']}")
            if item["summary"]:
                lines.append(f"   -> {item['summary'][:100]}")
            lines.append(f"   Accion: {item['action_type']}")
        lines.append("")

    if medium:
        lines.append(f"RELEVANTE ({len(medium)})")
        for idx, item in enumerate(medium, 1):
            lines.append(f"{idx}. {item['title'][:80]}")
        lines.append("")

    if low:
        lines.append(f"INFO ({len(low)})")
        for item in low[:5]:
            lines.append(f"- {item['title'][:60]}")

    digest = "\n".join(lines)
    print(digest)

    try:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({"chat_id": chat_id, "text": digest[:4000]}).encode()
            req = urllib.request.Request(
                tg_url, data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            print("[INTEL] Digest sent to Telegram")
    except Exception as e:
        print(f"[INTEL] Telegram send failed: {e}")

    for item in items:
        conn.execute(
            "UPDATE intelligence_items SET notified = 1 WHERE id = ?", (item["id"],)
        )
    conn.commit()
    conn.close()


def show_status():
    """Show current intelligence status."""
    conn = get_db()
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN relevance = 'HIGH' THEN 1 ELSE 0 END) as high,
            SUM(CASE WHEN relevance = 'MEDIUM' THEN 1 ELSE 0 END) as medium,
            SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) as unprocessed,
            MIN(created_at) as oldest,
            MAX(created_at) as newest
        FROM intelligence_items
        """).fetchone()

    sources = load_sources()
    print("[INTEL STATUS]")
    print(f"  Sources configured: {len(sources)}")
    print(f"  Total items: {stats['total']}")
    print(f"  HIGH: {stats['high']} | MEDIUM: {stats['medium']}")
    print(f"  Unprocessed: {stats['unprocessed']}")
    print(f"  Range: {stats['oldest'] or 'none'} -> {stats['newest'] or 'none'}")
    conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _load_env():
    """Load .env file into os.environ (setdefault — won't overwrite existing)."""
    env_path = DQIII8_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DQIII8 Intelligence Collector")
    parser.add_argument("--collect", action="store_true", help="Collect from sources")
    parser.add_argument(
        "--tier", type=str, default="1", help="Tiers to collect (e.g. 1 or 1,2,3)"
    )
    parser.add_argument(
        "--digest", action="store_true", help="Generate and send daily digest"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show intelligence status"
    )
    args = parser.parse_args()

    _load_env()

    if args.collect:
        collect(args.tier)
    elif args.digest:
        generate_digest()
    elif args.status:
        show_status()
    else:
        parser.print_help()
