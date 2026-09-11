#!/usr/bin/env python3
"""Full portfolio review across my-projects/ — red-team + stress-test pass per
project, utility assessment framed around personal/professional growth (not
revenue), except a small set of explicit profit-focus candidates. Designed to
run standalone inside tmux (NOT from inside an interactive Claude Code
session — recursive `claude --print` calls are unsupported, see
my-projects/intl-reports/RULE). Sends the final report to Telegram on
completion.

Usage (from an external tmux session, NOT from inside Claude Code):
    python3 bin/tools/portfolio_review.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/root/dqiii8")
PROJECTS_DIR = ROOT / "my-projects"
OUT_DIR = ROOT / "database" / "audit_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG = ROOT / "var" / "logs" / "portfolio_review.log"

# Explicit profit-focus anchor named by the operator; the synthesis pass may
# recommend 1-2 more from evidence, but this one is a given, not a candidate.
PROFIT_FOCUS_ANCHOR = "global-media-org"

# 0-file directories confirmed empty in the 2026-08-24 survey -- skip, nothing
# to review. Re-check if this list goes stale (a project could gain content).
SKIP = {"Data", "auto-report", "math-image-generator", "archived-projects", ".claude"}

PROJECT_PROMPT = """\
Estas revisando el proyecto "{name}" en {path}, como parte de una auditoria de \
cartera completa de un operador que dirige DQIII8 (motor de orquestacion IA). \
Contexto: el operador NO esta pidiendo un juicio de rentabilidad para la mayoria \
de proyectos -- quiere saber utilidad real para crecimiento personal/profesional \
y aprendizaje, salvo que el proyecto este explicitamente marcado como foco de lucro.

Es foco de lucro explicito: {is_profit_focus}

Haz esto, en este orden, y se concreto (cita archivos/lineas cuando aplique):

1. RED TEAM (seguridad/calidad): lee el codigo real (no solo README). Busca \
vulnerabilidades, secretos hardcodeados, deuda tecnica critica, cosas rotas. \
Si no hay nada grave, dilo explicitamente -- no inventes hallazgos.

2. STRESS TEST: si hay tests, ejecutalos (pytest/npm test/lo que aplique) y \
reporta el resultado real, no una suposicion. Si no hay tests, dilo y evalua \
que tan fragil parece el codigo sin ellos. Si el proyecto tiene un punto de \
entrada ejecutable razonable, intenta arrancarlo/importarlo para ver si al \
menos carga sin crashear.

3. UTILIDAD: evalua honestamente que aporta este proyecto -- aprendizaje \
tecnico, satisfaccion personal, cartera profesional, o si es cruft que deberia \
archivarse. Si es el foco de lucro explicito, evalua ademas su viabilidad real \
como negocio (mercado, madurez, que falta para ser viable).

4. VEREDICTO en una linea: mantener y seguir invirtiendo / mantener sin prisa / \
archivar.

Se breve donde puedas, exhaustivo solo donde importe. Maximo ~600 palabras.
"""

SYNTHESIS_PROMPT = """\
Tienes {n} informes de auditoria individuales de la cartera de proyectos de un \
operador que dirige DQIII8. El operador declaro explicitamente: quiere centrar \
2-3 proyectos como foco de lucro real (empezando por "global-media-org", que ya \
esta marcado como ancla), y el resto orientarlos a realizacion personal y \
profesional, NO a redito monetario. Su ambicion declarada es "mil millonario" \
via ese pequeno nucleo de foco de lucro, sabiendo que es un camino largo y \
tedioso, con muchas decisiones pendientes.

Aqui estan los informes:

{reports}

Escribe el informe final de sintesis (Markdown), con estas secciones:

## Resumen ejecutivo
3-5 frases. Estado real de la cartera, sin adornos.

## Hallazgos criticos (red team / stress test)
Lista solo lo que de verdad importa -- vulnerabilidades reales, cosas rotas que \
bloquean uso, deuda tecnica seria. Cita el proyecto.

## Foco de lucro (2-3 proyectos)
global-media-org ya esta confirmado. Recomienda 1-2 mas de la lista, con \
evidencia concreta de por que esos y no otros (madurez, ventaja real, lo que \
falta para ser viable). Se honesto si NINGUN otro proyecto esta listo -- no \
fuerces una recomendacion floja solo por completar el numero.

## Realizacion personal/profesional
Del resto, cuales aportan mas valor de aprendizaje/satisfaccion, y cuales son \
candidatos honestos a archivar porque no aportan ya nada.

## Proximos pasos concretos
5-8 acciones priorizadas, realistas para alguien con tiempo limitado, no una \
lista generica.

Se directo. El operador ya sabe que el camino es largo -- no se lo repitas, \
dale sustancia.
"""


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_claude(prompt: str, cwd: Path, timeout: int = 900) -> str:
    """Non-interactive claude -p call. Must run OUTSIDE any Claude Code
    session (this script is meant for tmux, not the CC tool loop) -- see
    module docstring."""
    result = subprocess.run(
        ["claude", "-p", prompt],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"ANTHROPIC_API_KEY": ""},
    )
    if result.returncode != 0:
        return f"[claude -p failed, exit {result.returncode}]\n{result.stderr[-2000:]}"
    return result.stdout.strip()


def discover_projects() -> list[Path]:
    projects = []
    for p in sorted(PROJECTS_DIR.iterdir()):
        if not p.is_dir() or p.name in SKIP:
            continue
        if not any(p.iterdir()):
            continue
        projects.append(p)
    return projects


def main() -> None:
    log("portfolio review starting")
    projects = discover_projects()
    log(f"{len(projects)} projects to review: {[p.name for p in projects]}")

    reports = []
    for i, proj in enumerate(projects, 1):
        name = proj.name
        is_profit = "SI" if name == PROFIT_FOCUS_ANCHOR else "no"
        log(f"[{i}/{len(projects)}] reviewing {name}...")
        t0 = time.time()
        try:
            prompt = PROJECT_PROMPT.format(name=name, path=proj, is_profit_focus=is_profit)
            report = run_claude(prompt, cwd=proj)
        except subprocess.TimeoutExpired:
            report = "[TIMEOUT after 900s]"
        except Exception as e:
            report = f"[ERROR: {e!r}]"
        elapsed = time.time() - t0
        log(f"[{i}/{len(projects)}] {name} done in {elapsed:.0f}s")
        reports.append(f"### {name}\n\n{report}\n")
        (OUT_DIR / f"portfolio_{name}.md").write_text(report, encoding="utf-8")

    log("all project reviews done, running synthesis pass...")
    synthesis_prompt = SYNTHESIS_PROMPT.format(n=len(reports), reports="\n\n---\n\n".join(reports))
    try:
        final_report = run_claude(synthesis_prompt, cwd=ROOT, timeout=1200)
    except Exception as e:
        final_report = (
            f"[synthesis failed: {e!r}]\n\nRaw per-project reports are in {OUT_DIR}/portfolio_*.md"
        )

    now = datetime.now(timezone.utc)
    out_path = OUT_DIR / f"portfolio_review_{now:%Y-%m-%d_%H%M%S}.md"
    out_path.write_text(final_report, encoding="utf-8")
    log(f"final report written to {out_path}")

    log("sending Telegram notification...")
    sys.path.insert(0, str(ROOT / "bin" / "core"))
    from notify import notify

    summary = final_report[:3500]
    msg = f"DQIII8 — Revision de cartera completa ({len(projects)} proyectos)\n\n{summary}"
    if len(final_report) > 3500:
        msg += f"\n\n[...informe completo en {out_path}]"
    res = notify(msg)
    log(f"telegram delivery: ok={res.ok if hasattr(res, 'ok') else res}")
    log("portfolio review finished")


if __name__ == "__main__":
    main()
