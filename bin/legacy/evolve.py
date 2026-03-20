#!/usr/bin/env python3
"""
/evolve — Converts consolidated instincts into actionable skills.

Flow:
  1. Reads instincts with confidence >= MIN_CONF OR times_applied >= MIN_APPLIED
  2. Groups by keyword root (first segment before '-')
  3. For clusters with 3+ instincts: generates skill draft in
     skills-registry/custom/evolved/[root].md
  4. Registers in skills-registry/INDEX.md with status PENDIENTE_REVISION
"""

import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
EVOLVED_DIR = JARVIS / "skills-registry" / "custom" / "evolved"
INDEX_MD = JARVIS / "skills-registry" / "INDEX.md"

MIN_CONF_DEFAULT = 0.7
MIN_APPLIED_DEFAULT = 5
MIN_CLUSTER_DEFAULT = 3


def keyword_root(kw: str) -> str:
    return kw.split("-")[0].lower()


def load_instincts(conn: sqlite3.Connection, min_conf: float, min_applied: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT keyword, pattern, confidence, times_applied, times_successful, project, created_at
        FROM instincts
        WHERE confidence >= ? OR times_applied >= ?
        ORDER BY confidence DESC, times_applied DESC
        """,
        (min_conf, min_applied),
    ).fetchall()
    return [
        {
            "keyword": r[0],
            "pattern": r[1],
            "confidence": r[2] or 0.5,
            "times_applied": r[3] or 0,
            "times_successful": r[4] or 0,
            "project": r[5] or "global",
            "created_at": r[6] or "",
        }
        for r in rows
    ]


def cluster_instincts(instincts: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for inst in instincts:
        root = keyword_root(inst["keyword"])
        clusters[root].append(inst)
    return dict(clusters)


def render_skill(root: str, members: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    projects = sorted({m["project"] for m in members})
    total_applied = sum(m["times_applied"] for m in members)
    avg_conf = sum(m["confidence"] for m in members) / len(members)

    lines = [
        f"# Skill: {root} (auto-evolved)",
        f"",
        f"**Generated:** {now}  ",
        f"**Source:** /evolve — {len(members)} instincts grouped  ",
        f"**Projects:** {', '.join(projects)}  ",
        f"**Average confidence:** {avg_conf:.2f}  ",
        f"**Total applied:** {total_applied}x  ",
        f"**Status:** PENDING_REVIEW  ",
        f"",
        f"## Description",
        f"",
        f"Auto-generated skill from consolidated instincts about `{root}`. "
        f"Review patterns, consolidate into actionable rules and change status to APPROVED.",
        f"",
        f"## Learned patterns",
        f"",
    ]
    for m in sorted(members, key=lambda x: -x["times_applied"]):
        conf_pct = int(m["confidence"] * 100)
        lines.append(f"### `{m['keyword']}` — conf: {conf_pct}%, applied: {m['times_applied']}x")
        lines.append(f"")
        lines.append(f"{m['pattern']}")
        lines.append(f"")

    lines += [
        f"## Consolidated rules (pending review)",
        f"",
        f"> TODO: Synthesize the above patterns into 3-5 concrete rules.",
        f"> Remove redundancies. Add code examples if applicable.",
        f"",
        f"## Anti-patterns",
        f"",
        f"> TODO: List what NOT to do according to the instincts.",
        f"",
        f"## When NOT to use this skill",
        f"",
        f"> TODO: Edge cases where this skill does not apply.",
    ]
    return "\n".join(lines) + "\n"


def register_in_index(root: str, member_count: int) -> bool:
    """Add PENDIENTE_REVISION row to INDEX.md. Returns True if newly added."""
    content = INDEX_MD.read_text(encoding="utf-8")
    skill_id = f"evolved/{root}"
    if skill_id in content:
        return False  # already registered

    entry = (
        f"| {skill_id} | /evolve auto ({member_count} instincts) "
        f"| ⏳ PENDING_REVIEW | — | Review + move to custom/ + status APPROVED |"
    )
    # Append to end of file
    INDEX_MD.write_text(content.rstrip() + "\n" + entry + "\n", encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="/evolve — cluster instincts into skills")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONF_DEFAULT)
    parser.add_argument("--min-applied", type=int, default=MIN_APPLIED_DEFAULT)
    parser.add_argument("--min-cluster", type=int, default=MIN_CLUSTER_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
    args = parser.parse_args()

    if not DB.exists():
        print(f"[evolve] DB not found: {DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB), timeout=5)
    instincts = load_instincts(conn, args.min_confidence, args.min_applied)
    conn.close()

    if not instincts:
        print(
            f"[evolve] No instincts (confidence>={args.min_confidence} OR applied>={args.min_applied})"
        )
        sys.exit(0)

    clusters = cluster_instincts(instincts)
    eligible = {r: m for r, m in clusters.items() if len(m) >= args.min_cluster}

    print(
        f"[evolve] {len(instincts)} eligible instincts | "
        f"{len(clusters)} clusters | {len(eligible)} with {args.min_cluster}+ members"
    )

    if not eligible:
        print(f"[evolve] No cluster reaches {args.min_cluster}+ instincts.")
        summary = ", ".join(f"{r}({len(m)})" for r, m in sorted(clusters.items()))
        print(f"  Current clusters: {summary}")
        sys.exit(0)

    if not args.dry_run:
        EVOLVED_DIR.mkdir(parents=True, exist_ok=True)

    generated = []
    for root, members in sorted(eligible.items()):
        skill_path = EVOLVED_DIR / f"{root}.md"
        content = render_skill(root, members)
        if args.dry_run:
            print(f"  [DRY-RUN] {skill_path.name} — {len(members)} instincts")
        else:
            skill_path.write_text(content, encoding="utf-8")
            registered = register_in_index(root, len(members))
            tag = " [new in INDEX]" if registered else " [already in INDEX]"
            print(f"  SKILL: {skill_path.name} — {len(members)} instincts{tag}")
            generated.append(root)

    if generated:
        print(
            f"\n[evolve] {len(generated)} skill(s) generated in skills-registry/custom/evolved/"
        )
        print(f"\nTo approve:")
        print(f"  1. Edit the .md: consolidate rules, add examples")
        print(f"  2. Change status in INDEX.md to '✅ APROBADA'")
        print(f"  3. Move from custom/evolved/ to custom/[name]/SKILL.md")


if __name__ == "__main__":
    main()
