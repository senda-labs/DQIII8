#!/usr/bin/env python3
"""
instinct_evolver.py — Clusters high-confidence instincts into skill drafts.

No embedding column available: clusters by keyword field (exact grouping).
Drafts land in .claude/skills/evolved/ with PENDIENTE_REVISION status.

Usage:
  --report    List clusters without writing files (default)
  --generate  Write SKILL.md drafts for clusters with 3+ instincts
  --demo      Use synthetic data to test output format
"""

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "database" / "dqiii8.db"
SKILLS_DIR = Path(__file__).parent.parent.parent / ".claude" / "skills" / "evolved"
MIN_CONFIDENCE = 0.7
MIN_CLUSTER_SIZE = 3


def load_instincts(demo: bool = False) -> list[dict]:
    if demo:
        return [
            {"id": i, "keyword": k, "pattern": p, "confidence": c, "project": proj}
            for i, k, p, c, proj in [
                (1, "async", "use asyncio for I/O tasks", 0.9, "dqiii8"),
                (2, "async", "avoid blocking calls in async context", 0.85, "dqiii8"),
                (3, "async", "use async with for resource managers", 0.8, "dqiii8"),
                (4, "paths", "use pathlib.Path not string concat", 0.9, "dqiii8"),
                (5, "paths", "always .as_posix() for cross-platform", 0.75, "dqiii8"),
                (6, "testing", "write tests before implementation", 0.95, "dqiii8"),
                (7, "testing", "mock at boundaries only", 0.8, "dqiii8"),
            ]
        ]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, keyword, pattern, confidence, project FROM instincts WHERE confidence > ?",
        (MIN_CONFIDENCE,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cluster_by_keyword(instincts: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for inst in instincts:
        key = (inst.get("keyword") or "").strip().lower()
        if key:
            clusters[key].append(inst)
    return dict(clusters)


def print_report(clusters: dict[str, list[dict]]) -> None:
    total = sum(len(v) for v in clusters.values())
    actionable = {k: v for k, v in clusters.items() if len(v) >= MIN_CLUSTER_SIZE}
    print(
        f"\n=== Instinct Evolution Report — {datetime.now().strftime('%Y-%m-%d')} ==="
    )
    print(f"High-confidence instincts: {total}")
    print(
        f"Clusters: {len(clusters)} | Actionable (>={MIN_CLUSTER_SIZE}): {len(actionable)}\n"
    )
    for keyword, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        flag = (
            ">>> SKILL CANDIDATE"
            if len(members) >= MIN_CLUSTER_SIZE
            else "    sub-threshold"
        )
        print(f"  [{len(members):2d}] {keyword:<25} {flag}")
        for m in members:
            print(f"         conf={m['confidence']:.2f}  {m['pattern'][:70]}")
    print()


def generate_drafts(clusters: dict[str, list[dict]]) -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    actionable = {k: v for k, v in clusters.items() if len(v) >= MIN_CLUSTER_SIZE}
    if not actionable:
        print("No clusters with 3+ instincts — nothing to generate.")
        return
    for keyword, members in actionable.items():
        slug = keyword.replace(" ", "-").replace("/", "-")
        path = SKILLS_DIR / f"{slug}.md"
        avg_conf = sum(m["confidence"] for m in members) / len(members)
        projects = sorted({m.get("project") or "dqiii8" for m in members})
        patterns = "\n".join(f"- {m['pattern']}" for m in members)
        content = f"""---
name: instinct-{slug}
description: Auto-evolved from {len(members)} instincts on keyword '{keyword}'. Avg confidence: {avg_conf:.2f}. STATUS: PENDIENTE_REVISION
type: feedback
status: PENDIENTE_REVISION
source_keyword: {keyword}
instinct_count: {len(members)}
avg_confidence: {avg_conf:.2f}
projects: {', '.join(projects)}
generated: {datetime.now().strftime('%Y-%m-%d')}
---

# {keyword.title()} — Evolved Skill (PENDIENTE_REVISION)

> Auto-generated from {len(members)} high-confidence instincts. Review before activating.

## Patterns observed

{patterns}

## How to apply

Apply these patterns consistently when working with '{keyword}' in: {', '.join(projects)}.

## Activation

Remove the `status: PENDIENTE_REVISION` line and move to `.claude/skills/` to activate.
"""
        path.write_text(content, encoding="utf-8")
        print(f"  Draft written: {path.relative_to(Path.cwd())}")
    print(f"\n{len(actionable)} draft(s) in {SKILLS_DIR.relative_to(Path.cwd())}")
    print("Review and remove PENDIENTE_REVISION to activate.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Instinct evolver — clusters instincts into skill drafts"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--report", action="store_true", default=True, help="List clusters (default)"
    )
    group.add_argument("--generate", action="store_true", help="Write SKILL.md drafts")
    group.add_argument("--demo", action="store_true", help="Use synthetic data")
    args = parser.parse_args()

    demo = args.demo
    instincts = load_instincts(demo=demo)
    clusters = cluster_by_keyword(instincts)
    print_report(clusters)
    if args.generate:
        generate_drafts(clusters)
    elif args.demo:
        generate_drafts(clusters)


if __name__ == "__main__":
    main()
