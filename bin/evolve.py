#!/usr/bin/env python3
"""
/evolve — Convierte instincts consolidados en skills accionables.

Flujo:
  1. Lee instincts con confidence >= MIN_CONF OR times_applied >= MIN_APPLIED
  2. Agrupa por raiz del keyword (primer segmento antes de '-')
  3. Para clusters con 3+ instincts: genera skill draft en
     skills-registry/custom/evolved/[raiz].md
  4. Registra en skills-registry/INDEX.md con status PENDIENTE_REVISION
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
        f"**Generada:** {now}  ",
        f"**Fuente:** /evolve — {len(members)} instincts agrupados  ",
        f"**Proyectos:** {', '.join(projects)}  ",
        f"**Confianza media:** {avg_conf:.2f}  ",
        f"**Total aplicado:** {total_applied}x  ",
        f"**Status:** PENDIENTE_REVISION  ",
        f"",
        f"## Descripcion",
        f"",
        f"Skill auto-generada desde instincts consolidados sobre `{root}`. "
        f"Revisar patrones, consolidar en reglas accionables y cambiar status a APROBADA.",
        f"",
        f"## Patrones aprendidos",
        f"",
    ]
    for m in sorted(members, key=lambda x: -x["times_applied"]):
        conf_pct = int(m["confidence"] * 100)
        lines.append(f"### `{m['keyword']}` — conf: {conf_pct}%, aplicado: {m['times_applied']}x")
        lines.append(f"")
        lines.append(f"{m['pattern']}")
        lines.append(f"")

    lines += [
        f"## Reglas consolidadas (pendiente revision)",
        f"",
        f"> TODO: Sintetizar los patrones anteriores en 3-5 reglas concretas.",
        f"> Eliminar redundancias. Anadir ejemplos de codigo si aplica.",
        f"",
        f"## Anti-patrones",
        f"",
        f"> TODO: Listar que NO hacer segun los instincts.",
        f"",
        f"## Cuando NO usar esta skill",
        f"",
        f"> TODO: Casos limite donde esta skill no aplica.",
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
        f"| ⏳ PENDIENTE_REVISION | — | Revisar + mover a custom/ + status APROBADA |"
    )
    # Append to end of file
    INDEX_MD.write_text(content.rstrip() + "\n" + entry + "\n", encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="/evolve — cluster instincts into skills")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONF_DEFAULT)
    parser.add_argument("--min-applied", type=int, default=MIN_APPLIED_DEFAULT)
    parser.add_argument("--min-cluster", type=int, default=MIN_CLUSTER_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="No escribe archivos")
    args = parser.parse_args()

    if not DB.exists():
        print(f"[evolve] DB not found: {DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB), timeout=5)
    instincts = load_instincts(conn, args.min_confidence, args.min_applied)
    conn.close()

    if not instincts:
        print(
            f"[evolve] Sin instincts (confidence>={args.min_confidence} OR applied>={args.min_applied})"
        )
        sys.exit(0)

    clusters = cluster_instincts(instincts)
    eligible = {r: m for r, m in clusters.items() if len(m) >= args.min_cluster}

    print(
        f"[evolve] {len(instincts)} instincts elegibles | "
        f"{len(clusters)} clusters | {len(eligible)} con {args.min_cluster}+ miembros"
    )

    if not eligible:
        print(f"[evolve] Ningún cluster alcanza {args.min_cluster}+ instincts.")
        summary = ", ".join(f"{r}({len(m)})" for r, m in sorted(clusters.items()))
        print(f"  Clusters actuales: {summary}")
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
            tag = " [nuevo en INDEX]" if registered else " [ya en INDEX]"
            print(f"  SKILL: {skill_path.name} — {len(members)} instincts{tag}")
            generated.append(root)

    if generated:
        print(
            f"\n[evolve] {len(generated)} skill(s) generada(s) en skills-registry/custom/evolved/"
        )
        print(f"\nPara aprobar:")
        print(f"  1. Editar el .md: consolidar reglas, anadir ejemplos")
        print(f"  2. Cambiar status en INDEX.md a '✅ APROBADA'")
        print(f"  3. Mover de custom/evolved/ a custom/[nombre]/SKILL.md")


if __name__ == "__main__":
    main()
