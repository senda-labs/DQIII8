#!/usr/bin/env python3
"""DQIII8 Intelligence Collector — automated knowledge gathering.

Collects news, updates, and papers from configured sources.
Classifies relevance using Groq ($0).
Generates daily digest for Telegram.
Auto-generates knowledge chunks for HIGH relevance items.

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
import hashlib
from datetime import datetime
from pathlib import Path

DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = DQIII8_ROOT / "database" / "jarvis_metrics.db"
SOURCES_PATH = DQIII8_ROOT / "config" / "intelligence_sources.json"
KNOWLEDGE_ROOT = DQIII8_ROOT / "knowledge"


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


def fetch_web_content(url):
    """Fetch web content using curl."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "30", url],
            capture_output=True,
            text=True,
            timeout=35,
        )
        if result.returncode == 0:
            return result.stdout[:10000]
    except Exception:
        pass
    return ""


def extract_items_from_content(content, source):
    """Use Groq to extract news items from raw content."""
    prompt = (
        f"Extract the 5 most recent news items from this content.\n"
        f"Source: {source['name']} ({source['url']})\n"
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
        print(f"  Error extracting from {source['name']}: {e}")
    return []


def classify_item(item, source):
    """Classify relevance for DQ using Groq ($0)."""
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
    except Exception:
        pass
    return {"relevance": "LOW", "action": "monitor", "affects": "none"}


def store_item(item, source, classification):
    """Store classified item in DB, skip duplicates by title."""
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
                item.get("url", source["url"]),
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


def collect(tiers="1"):
    """Collect from all sources of specified tiers."""
    sources = load_sources(tiers)
    print(f"[INTEL] Collecting from {len(sources)} sources (tiers: {tiers})")

    total_items = 0
    for source in sources:
        print(f"  [{source['name']}] Fetching...")
        content = fetch_web_content(source["url"])
        if not content:
            print(f"  [{source['name']}] No content retrieved")
            continue

        items = extract_items_from_content(content, source)
        for item in items[:5]:
            classification = classify_item(item, source)
            stored = store_item(item, source, classification)
            if stored:
                total_items += 1
                relevance = classification.get("relevance", "?")
                print(f"    {relevance}: {item.get('title', '?')[:60]}")

    print(f"[INTEL] Collected {total_items} new items")


def generate_digest():
    """Generate daily digest and send via Telegram."""
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

    # Send via Telegram
    try:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            import urllib.request

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({"chat_id": chat_id, "text": digest[:4000]}).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
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


def _load_env():
    """Source .env for API keys."""
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
