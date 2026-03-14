#!/usr/bin/env python3
"""
JARVIS — OrchestratorLoop
Monitor de sesión autónoma que detecta ESCALATE del PermissionAnalyzer
y pausa el ciclo para requerir intervención humana.

Uso:
    python3 bin/orchestrator_loop.py --project <nombre> [--cycles N]
    JARVIS_MODE=autonomous python3 bin/orchestrator_loop.py --project myproject
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")
MAX_CYCLES = int(os.environ.get("ORCHESTRATOR_MAX_CYCLES", "20"))


class OrchestratorLoop:
    """Loop de monitorización que detecta bloqueos de permisos y escala al humano."""

    def __init__(self) -> None:
        self._has_escalate = False

    # ── Queries ─────────────────────────────────────────────────────────────

    def check_rejections(self) -> list[dict]:
        """
        Lee rechazos recientes de permission_decisions para la sesión actual.
        Separa los ESCALATE de los DENY normales y activa _has_escalate si hay alguno.
        """
        pending: list[dict] = []
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT tool_name, action_detail, decision,
                       reason AS rejection_reason, suggested_fix, risk_level
                FROM permission_decisions
                WHERE session_id = ?
                  AND decision IN ('DENY', 'ESCALATE')
                  AND timestamp > datetime('now', '-1 hour')
                ORDER BY timestamp DESC
                LIMIT 20
                """,
                (SESSION_ID,),
            ).fetchall()
            conn.close()
            pending = [dict(r) for r in rows]
        except Exception:
            pass

        # Separar ESCALATE de DENY normales
        escalates = [
            r
            for r in pending
            if r.get("decision") == "ESCALATE"
            or "ESCALATE" in r.get("rejection_reason", "")
            or "Requiere decisión humana" in r.get("rejection_reason", "")
        ]

        if escalates:
            print("\n🚨 ESCALATE DETECTADO — requiere intervención humana:")
            for e in escalates:
                print(f"   Tool: {e['tool_name']}")
                print(f"   Razón: {e['rejection_reason'][:80]}")
                fix = e.get("suggested_fix") or "N/A"
                print(f"   Fix sugerido: {fix[:80]}")
            print("\n   El loop se pausará tras el ciclo actual.")
            self._has_escalate = True

        return pending

    def analyze(self, project: str) -> dict:
        """
        Lee estado del proyecto y verifica rechazos pendientes.
        Returns contexto del ciclo actual.
        """
        rejections = self.check_rejections()

        recent_actions: list[dict] = []
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT tool_used, file_path, action_type, success, timestamp
                FROM agent_actions
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
                """,
                (SESSION_ID,),
            ).fetchall()
            conn.close()
            recent_actions = [dict(r) for r in rows]
        except Exception:
            pass

        return {
            "project": project,
            "session_id": SESSION_ID,
            "recent_actions": recent_actions,
            "rejections": rejections,
            "has_escalate": self._has_escalate,
        }

    # ── Loop principal ───────────────────────────────────────────────────────

    def run(self, project: str, max_cycles: int = MAX_CYCLES) -> None:
        """
        Ejecuta el loop de monitorización.
        Se pausa automáticamente si detecta un ESCALATE.
        """
        self._has_escalate = False
        print(f"🔄 OrchestratorLoop iniciado — proyecto: {project} | max_cycles: {max_cycles}")

        for cycle in range(1, max_cycles + 1):
            print(f"\n── Ciclo {cycle}/{max_cycles} ──────────────────────────────")

            context = self.analyze(project)

            # Pausa inmediata si hay ESCALATE
            if self._has_escalate:
                print("\n⚠️  Loop pausado por ESCALATE.")
                print("   Resuelve el bloqueante humano y relanza con:")
                print(
                    f"   JARVIS_MODE=autonomous "
                    f"python3 bin/orchestrator_loop.py --project {project}"
                )
                sys.exit(1)

            rejections = context["rejections"]
            if rejections:
                deny_count = sum(1 for r in rejections if r.get("decision") == "DENY")
                print(f"   ⚠  {deny_count} rechazo(s) DENY en la última hora")
            else:
                print("   ✓  Sin rechazos recientes")

            print(f"   Acciones recientes: {len(context['recent_actions'])}")

        print(f"\n✅ OrchestratorLoop completado — {max_cycles} ciclos sin ESCALATE")


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS OrchestratorLoop")
    parser.add_argument("--project", required=True, help="Nombre del proyecto")
    parser.add_argument(
        "--cycles",
        type=int,
        default=MAX_CYCLES,
        help=f"Máximo de ciclos (default: {MAX_CYCLES})",
    )
    args = parser.parse_args()

    loop = OrchestratorLoop()
    loop.run(project=args.project, max_cycles=args.cycles)


if __name__ == "__main__":
    main()
