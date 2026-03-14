#!/usr/bin/env python3
"""
JARVIS — PermissionAnalyzer v2
Evaluación centralizada de permisos para hooks pre_tool_use.

Mejoras v2:
  A — SQLite timeout=10 en todas las conexiones
  B — ALLOWED_DELETIONS para rutas de caché seguras
  C — Historial de intentos + ESCALATE para loops infinitos
"""

import os
import re
import sqlite3
from pathlib import Path

# ── Configuración ───────────────────────────────────────────────────────────
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")
JARVIS_MODE = os.environ.get("JARVIS_MODE", "supervised")  # autonomous | supervised

# ── Constantes de riesgo ────────────────────────────────────────────────────
BLOCKED_PATHS = [
    ".env",
    "secrets",
    "jarvis_metrics.db",
    ".claude/settings.json",
    "CLAUDE.md",
    "schema.sql",
    ".git/",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
]

# Patrones regex para comandos destructivos
HIGH_RISK_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf /anything (includes rm -rf /)
    r"rm\s+-rf\s+~",  # rm -rf ~
    r"rm\s+-rf\s+\$HOME",  # rm -rf $HOME
    r"DROP\s+TABLE",  # SQL destructivo
    r"DELETE\s+FROM\s+agent_actions",  # borrar métricas JARVIS
    r"DROP\s+DATABASE",
    r">\s+/dev/sda",  # sobreescribir disco
    r"\bmkfs\b",  # formatear partición
    r"\bdd\b.*\bif=",  # dd de disco
    r"chmod\s+777\s+/",  # permisos root inseguros
    r":\(\)\s*\{.*:\|:.*\}",  # fork bomb
]

# Carpetas que se pueden borrar sin riesgo (limpieza de caché)
ALLOWED_DELETIONS = [
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "tmp",
    "/tmp/",
    ".mypy_cache",
    "*.pyc",
    ".ruff_cache",
]

MAX_SAME_REJECTION = 2  # Tras 2 rechazos idénticos → ESCALATE


class PermissionAnalyzer:
    """Evaluador centralizado de permisos para herramientas de Claude Code."""

    def evaluate(self, tool: str, inp: dict) -> dict:
        """
        Evalúa si una herramienta puede ejecutarse.

        Returns dict con keys: decision, reason, risk_level,
        rule_triggered, suggested_fix.
        decision ∈ {APPROVE, DENY, ESCALATE}
        """
        # MEJORA C — ESCALATE check antes que todo (cierra loops infinitos)
        detail = str(inp.get("file_path", inp.get("command", "")))
        escalate = self._check_repeat_rejections(tool, detail)
        if escalate:
            return escalate

        # Check paths bloqueados (Write, Edit, MultiEdit)
        if tool in ("Edit", "Write", "MultiEdit"):
            path = inp.get("file_path", inp.get("path", ""))
            for blocked in BLOCKED_PATHS:
                if blocked in path:
                    return self._deny(
                        tool,
                        path,
                        f"Escritura bloqueada en '{path}'. "
                        "Modifica este archivo manualmente si es necesario.",
                        "CRITICAL",
                        f"blocked_path:{blocked}",
                        "Editar directamente desde terminal o pedir al usuario.",
                    )

        # MEJORA B — Check comandos de alto riesgo con excepción ALLOWED_DELETIONS
        if tool == "Bash":
            cmd = inp.get("command", "")
            for pattern in HIGH_RISK_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    # Excepción: rutas seguras de limpieza de caché
                    is_safe_deletion = any(safe in cmd for safe in ALLOWED_DELETIONS)
                    if is_safe_deletion:
                        break  # Aprobar — es limpieza de caché

                    if JARVIS_MODE == "autonomous":
                        return self._deny(
                            tool,
                            cmd,
                            f"Comando de alto riesgo en modo autónomo: {cmd[:80]}",
                            "HIGH",
                            f"high_risk_pattern:{pattern}",
                            "Usar ALLOWED_DELETIONS o ejecutar en modo supervisado.",
                        )
                    else:
                        return self._deny(
                            tool,
                            cmd,
                            f"Comando bloqueado: '{cmd[:80]}'",
                            "CRITICAL",
                            f"high_risk_pattern:{pattern}",
                            "Este comando es destructivo e irreversible.",
                        )

        return {
            "decision": "APPROVE",
            "reason": "OK",
            "risk_level": "LOW",
            "rule_triggered": None,
            "suggested_fix": None,
        }

    def _deny(
        self,
        tool: str,
        detail: str,
        reason: str,
        risk_level: str,
        rule_triggered: str,
        suggested_fix: str,
    ) -> dict:
        return {
            "decision": "DENY",
            "reason": reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
            "suggested_fix": suggested_fix,
        }

    def _check_repeat_rejections(self, tool: str, detail: str) -> dict | None:
        """
        Si el mismo tool+action_detail ha sido rechazado MAX_SAME_REJECTION
        veces en esta sesión → devolver ESCALATE en lugar de DENY.

        ESCALATE significa: el OrchestratorLoop debe notificar al usuario
        humano, no reintentar solo.
        """
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)  # MEJORA A
            row = conn.execute(
                """
                SELECT COUNT(*) FROM permission_decisions
                WHERE session_id = ?
                  AND tool_name = ?
                  AND action_detail LIKE ?
                  AND decision = 'DENY'
                  AND timestamp > datetime('now', '-2 hours')
                """,
                (SESSION_ID, tool, f"%{detail[:50]}%"),
            ).fetchone()
            conn.close()

            count = row[0] if row else 0
            if count >= MAX_SAME_REJECTION:
                return {
                    "decision": "ESCALATE",
                    "reason": (
                        f"Acción '{tool}: {detail[:60]}' rechazada "
                        f"{count} veces en esta sesión. "
                        "Requiere decisión humana."
                    ),
                    "risk_level": "HIGH",
                    "rule_triggered": f"repeat_rejection:{count}",
                    "suggested_fix": (
                        "El OrchestratorLoop debe pausar y notificar "
                        "al usuario. El agente necesita una estrategia "
                        "diferente que no requiera esta acción bloqueada. "
                        f"Intentos previos: {count}."
                    ),
                }
        except Exception:
            pass
        return None

    def _check_budget(self, tool: str, inp: dict) -> dict | None:
        """Placeholder: verificación de presupuesto de tokens por sesión."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)  # MEJORA A
            # Future: query sessions table for token budget enforcement
            conn.close()
        except Exception:
            pass
        return None


# ── Funciones standalone (usadas por pre_tool_use.py) ───────────────────────


def record_decision(tool: str, inp: dict, result: dict) -> None:
    """Registra decisiones APPROVE en la BD."""
    if result["decision"] != "APPROVE":
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)  # MEJORA A
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason, risk_level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                str(inp.get("file_path", inp.get("command", "")))[:200],
                "APPROVE",
                result.get("reason", "OK"),
                result.get("risk_level", "LOW"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_rejection(tool: str, inp: dict, result: dict) -> None:
    """Registra DENY y ESCALATE en la BD."""
    if result["decision"] not in ("DENY", "ESCALATE"):
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)  # MEJORA A
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason,
                 risk_level, rule_triggered, suggested_fix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                str(inp.get("file_path", inp.get("command", "")))[:200],
                result["decision"],
                result.get("reason", ""),
                result.get("risk_level", ""),
                result.get("rule_triggered", ""),
                result.get("suggested_fix", ""),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
