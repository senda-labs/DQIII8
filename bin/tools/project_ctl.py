#!/usr/bin/env python3
"""project_ctl.py — CLI for the project_context SSOT (Stage 2, DB attribution rebuild).

Usage:
  python3 bin/tools/project_ctl.py set <project> [--scope global|<session_id>]
  python3 bin/tools/project_ctl.py get [--scope global|<session_id>]
  python3 bin/tools/project_ctl.py end [--scope global|<session_id>]
  python3 bin/tools/project_ctl.py value <project> <tipo> <importe_eur> [--nota TEXT]
  python3 bin/tools/project_ctl.py status <project> <status>
  python3 bin/tools/project_ctl.py budget set <project> <presupuesto_eur>
  python3 bin/tools/project_ctl.py budget-status [<project>]
  python3 bin/tools/project_ctl.py roi [<project>]
  python3 bin/tools/project_ctl.py rate set <rate_eur_hour> [--basis TEXT]
  python3 bin/tools/project_ctl.py rate get

(Stage 8 — see /root/.claude/plans/distributed-wobbling-gem.md.)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project_context import (
    end_project,
    get_budget_status,
    get_labor_rate,
    get_project,
    get_project_roi,
    get_project_status,
    known_projects,
    record_project_value,
    set_labor_rate,
    set_project,
    set_project_budget,
    set_project_status,
)


def _nd(value):
    """Render NULL (labor_rates empty) as 'N/D' instead of a literal 'None'."""
    return "N/D" if value is None else value


def main() -> int:
    parser = argparse.ArgumentParser(description="Get/set/end the current project declaration.")
    sub = parser.add_subparsers(dest="action", required=True)

    p_set = sub.add_parser("set", help="Declare the current project.")
    p_set.add_argument("project")
    p_set.add_argument("--scope", default="global")

    p_get = sub.add_parser("get", help="Show the current project for a scope.")
    p_get.add_argument("--scope", default="global")

    p_end = sub.add_parser("end", help="Close the open declaration for a scope.")
    p_end.add_argument("--scope", default="global")

    p_value = sub.add_parser("value", help="Record a project_value row.")
    p_value.add_argument("project")
    p_value.add_argument("tipo", choices=["fee_cobrado", "hito_entregado", "valor_estimado"])
    p_value.add_argument("importe_eur", type=float)
    p_value.add_argument("--nota", default=None)

    p_status = sub.add_parser("status", help="Set the status on the open project_context row(s).")
    p_status.add_argument("project")
    p_status.add_argument("status", choices=["activo", "pausado", "entregado", "abandonado"])

    p_budget = sub.add_parser("budget", help="Manage project budget targets.")
    budget_sub = p_budget.add_subparsers(dest="budget_action", required=True)
    p_budget_set = budget_sub.add_parser("set", help="Set the budget target for a project.")
    p_budget_set.add_argument("project")
    p_budget_set.add_argument("presupuesto_eur", type=float)

    p_budget_status = sub.add_parser("budget-status", help="Show budget deviation.")
    p_budget_status.add_argument("project", nargs="?", default=None)

    p_roi = sub.add_parser("roi", help="Show project ROI.")
    p_roi.add_argument("project", nargs="?", default=None)

    p_rate = sub.add_parser("rate", help="Manage the labor rate used to price human hours.")
    rate_sub = p_rate.add_subparsers(dest="rate_action", required=True)
    p_rate_set = rate_sub.add_parser("set", help="Insert a new labor rate.")
    p_rate_set.add_argument("rate_eur_hour", type=float)
    p_rate_set.add_argument("--basis", default=None)
    rate_sub.add_parser("get", help="Show the current labor rate.")

    args = parser.parse_args()

    if args.action == "set":
        try:
            set_project(args.project, scope=args.scope, declared_by="cli")
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(f"known projects: {', '.join(sorted(known_projects()))}", file=sys.stderr)
            return 1
        print(f"project set to '{args.project}' for scope '{args.scope}'.")
        return 0

    if args.action == "get":
        project = get_project(args.scope)
        print(project if project else f"(no project declared for scope '{args.scope}')")
        return 0

    if args.action == "end":
        closed = end_project(args.scope)
        print("closed." if closed else f"(no open declaration for scope '{args.scope}')")
        return 0

    if args.action == "value":
        try:
            record_project_value(args.project, args.tipo, args.importe_eur, nota=args.nota)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(f"known projects: {', '.join(sorted(known_projects()))}", file=sys.stderr)
            return 1
        print(f"recorded {args.tipo} {args.importe_eur} EUR for '{args.project}'.")
        return 0

    if args.action == "status":
        try:
            set_project_status(args.project, args.status)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(f"known projects: {', '.join(sorted(known_projects()))}", file=sys.stderr)
            return 1
        print(f"status for '{args.project}' set to '{args.status}'.")
        return 0

    if args.action == "budget":
        if args.budget_action == "set":
            try:
                set_project_budget(args.project, args.presupuesto_eur)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                print(f"known projects: {', '.join(sorted(known_projects()))}", file=sys.stderr)
                return 1
            print(f"budget for '{args.project}' set to {args.presupuesto_eur} EUR.")
            return 0
        return 1

    if args.action == "budget-status":
        rows = get_budget_status(args.project)
        if not rows:
            print("(no budget data)")
            return 0
        for r in rows:
            # coste_humano_eur/coste_total_eur/desviacion_pct are NULL (not 0)
            # when labor_rates has no row yet.
            print(
                f"{r['project']}: presupuesto={r['presupuesto_eur']} EUR, "
                f"coste_total={_nd(r['coste_total_eur'])} EUR "
                f"(humano={_nd(r['coste_humano_eur'])} EUR / {r['human_hours']}h, "
                f"infra={r['coste_infra_eur']} EUR), "
                f"desviacion={_nd(r['desviacion_pct'])}%"
            )
        return 0

    if args.action == "roi":
        rows = get_project_roi(args.project)
        if not rows:
            print("(no ROI data)")
            return 0
        for r in rows:
            print(
                f"{r['project']}: ingresos={r['ingresos_eur']} EUR, "
                f"coste_humano={_nd(r['coste_humano_eur'])} EUR ({r['human_hours']}h), "
                f"coste_infra={r['coste_infra_eur']} EUR, roi={_nd(r['roi_eur'])} EUR "
                f"(coste_tecnico_usd_informativo={r['coste_tecnico_usd_informativo']})"
            )
        return 0

    if args.action == "rate":
        if args.rate_action == "set":
            try:
                set_labor_rate(args.rate_eur_hour, basis=args.basis)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(f"labor rate set to {args.rate_eur_hour} EUR/h.")
            return 0
        if args.rate_action == "get":
            print(f"{get_labor_rate()} EUR/h")
            return 0
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
