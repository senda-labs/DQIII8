#!/usr/bin/env python3
"""
JARVIS — PermissionAnalyzer v3
Evaluación centralizada de permisos para hooks pre_tool_use.

v2: SQLite timeout + ALLOWED_DELETIONS + ESCALATE loop
v3: Dual-channel rejections (BD + JSON buzón) + budget check +
    autonomous auto-approve + FIX ESCALATE count (DENY+ESCALATE)
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

# ── Configuración ───────────────────────────────────────────────────────────
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")
JARVIS_MODE = os.environ.get("JARVIS_MODE", "supervised")

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

HIGH_RISK_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf /anything (includes rm -rf /)
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\$HOME",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM\s+agent_actions",
    r"DROP\s+DATABASE",
    r">\s+/dev/sda",
    r"\bmkfs\b",
    r"\bdd\b.*\bif=",
    r"chmod\s+777\s+/",
    r":\(\)\s*\{.*:\|:.*\}",  # fork bomb
]

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

# Directorios de proyecto siempre seguros para escritura
SAFE_PROJECT_DIRS = [
    "/root/math-image-generator",
    "/root/content-automation-faceless/output",
    "/tmp/",
]

# Herramientas que se auto-aprueban en modo autónomo (tras pasar checks)
AUTO_APPROVE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
}

MAX_SESSION_COST_USD = 5.0
MAX_SAME_REJECTION = 2  # Tras 2 rechazos idénticos → ESCALATE

# Hints informativos por tipo de denegación (ayudan a Claude a autocorregirse)
DENIAL_HINTS: dict[str, str] = {
    "blocked_path:.env": (
        "Usa os.environ['KEY'] para leer variables temporales. "
        "O usa export KEY=valor en bash sin tocar el archivo."
    ),
    "blocked_path:schema.sql": (
        "Añade la migración SQL en un archivo nuevo: "
        "database/migrations/YYYYMMDD_descripcion.sql"
    ),
    "blocked_path:CLAUDE.md": (
        "Las instrucciones del sistema no se modifican desde código. "
        "El usuario las actualiza manualmente."
    ),
    "blocked_path:jarvis_metrics.db": (
        "Usa INSERT/UPDATE via sqlite3 con el wrapper existente. "
        "No modificar el archivo de BD directamente."
    ),
    "high_risk_pattern": (
        "Usa rutas relativas específicas en lugar de wildcards. "
        "O añade el patrón a ALLOWED_DELETIONS si es limpieza de caché."
    ),
    "budget_exceeded": (
        "Dividir el objetivo en subtareas más pequeñas. " "Iniciar nueva sesión con j --autonomous"
    ),
    "repeat_rejection": (
        "Esta acción fue rechazada múltiples veces. "
        "Cambia de estrategia: usa una herramienta diferente o "
        "consulta al usuario antes de reintentar."
    ),
}


class PermissionAnalyzer:
    """Evaluador centralizado de permisos para herramientas de Claude Code."""

    def evaluate(self, tool: str, inp: dict, session_id: str | None = None) -> dict:
        """
        Evalúa si una herramienta puede ejecutarse.
        decision ∈ {APPROVE, DENY, ESCALATE}

        session_id: ID de sesión del evento hook (prioridad sobre variable de entorno).
        """
        _session = session_id or SESSION_ID
        detail = str(inp.get("file_path", inp.get("command", "")))

        # 0a. Directorios de proyecto seguros — fast-path sin restricciones
        if tool in ("Write", "Edit", "MultiEdit", "Bash"):
            if any(safe in detail for safe in SAFE_PROJECT_DIRS):
                return self._approve("Directorio de proyecto seguro", "LOW", "safe_project_dir")

        # 0b. learned_approvals — fast-path para patrones históricamente seguros
        if self._is_learned_safe(tool, detail):
            return self._approve("Patrón aprobado por historial", "LOW", "learned_approval")

        # 1. ESCALATE — cierra loops infinitos
        escalate = self._check_repeat_rejections(tool, detail, _session)
        if escalate:
            return escalate

        # 2. Budget — bloquear si se supera el presupuesto de sesión
        budget_deny = self._check_budget(_session)
        if budget_deny:
            return budget_deny

        # 3. Paths bloqueados (Write, Edit, MultiEdit)
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

        # 3b. Resource claims — bloquear si otro agente tiene el archivo
        if tool in ("Edit", "Write", "MultiEdit"):
            path = inp.get("file_path", inp.get("path", ""))
            claim_deny = self._check_resource_claim(tool, path, _session)
            if claim_deny:
                return claim_deny

        # 4. Comandos de alto riesgo con excepción ALLOWED_DELETIONS
        if tool == "Bash":
            cmd = inp.get("command", "")
            for pattern in HIGH_RISK_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    is_safe_deletion = any(safe in cmd for safe in ALLOWED_DELETIONS)
                    if is_safe_deletion:
                        break
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

        # 5. Modo autónomo — auto-aprobar herramientas estándar (tras checks)
        if JARVIS_MODE == "autonomous" and tool in AUTO_APPROVE_TOOLS:
            return self._approve("autonomous_mode")

        return self._approve()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _approve(
        self,
        reason: str = "OK",
        risk_level: str = "LOW",
        rule_triggered: str | None = None,
    ) -> dict:
        return {
            "decision": "APPROVE",
            "reason": reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
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
        # Enriquecer reason con hint de autocorrección (MEJORA 3)
        enriched_reason = reason
        if rule_triggered:
            for key, hint in DENIAL_HINTS.items():
                if key in rule_triggered:
                    enriched_reason = f"{reason} | Alternativa: {hint}"
                    break
        return {
            "decision": "DENY",
            "reason": enriched_reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
            "suggested_fix": suggested_fix,
        }

    def _check_repeat_rejections(
        self, tool: str, detail: str, session_id: str | None = None
    ) -> dict | None:
        """
        Si el mismo tool+action_detail ha sido rechazado MAX_SAME_REJECTION
        veces (DENY o ESCALATE) en esta sesión → devolver ESCALATE.
        FIX C: cuenta tanto DENY como ESCALATE.
        """
        _session = session_id or SESSION_ID
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT COUNT(*) FROM permission_decisions
                WHERE session_id = ?
                  AND tool_name = ?
                  AND action_detail LIKE ?
                  AND decision IN ('DENY', 'ESCALATE')
                  AND timestamp > datetime('now', '-2 hours')
                """,
                (_session, tool, f"%{detail[:50]}%"),
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
                        "El OrchestratorLoop debe pausar y notificar al usuario. "
                        "El agente necesita una estrategia diferente que no "
                        "requiera esta acción bloqueada. "
                        f"Intentos previos: {count}."
                    ),
                }
        except Exception:
            pass
        return None

    def _is_learned_safe(self, tool: str, detail: str) -> bool:
        """
        Comprueba si este tool+pattern ya fue aprobado >= 3 veces (active=1).
        Fast-path antes de todos los checks de seguridad.
        """
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT id FROM learned_approvals
                WHERE tool_name = ?
                  AND ? LIKE '%' || pattern || '%'
                  AND active = 1
                LIMIT 1
                """,
                (tool, detail),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def _check_resource_claim(self, tool: str, path: str, session_id: str) -> dict | None:
        """
        Bloquea si otro agente/sesión tiene un claim activo sobre este recurso.
        Claims expiran automáticamente por TTL (expires_at).
        """
        if not path:
            return None
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT agent, session_id FROM resource_claims
                WHERE resource = ?
                  AND session_id != ?
                  AND expires_at > datetime('now')
                LIMIT 1
                """,
                (path, session_id),
            ).fetchone()
            conn.close()
            if row:
                holder_agent, holder_session = row
                return self._deny(
                    tool,
                    path,
                    f"Recurso '{path}' bloqueado por agente '{holder_agent}' "
                    f"(sesión {holder_session[:8]}…). Espera a que expire el claim.",
                    "MEDIUM",
                    "resource_claim",
                    "Espera 30 min o pide al agente propietario que libere el recurso.",
                )
        except Exception:
            pass
        return None

    def _check_budget(self, session_id: str) -> dict | None:
        """Bloquea si el coste estimado de la sesión supera MAX_SESSION_COST_USD."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_used),0) FROM agent_actions "
                "WHERE session_id=? AND timestamp > datetime('now','-1 hour')",
                (session_id,),
            ).fetchone()
            conn.close()
            session_tokens = row[0] if row else 0
            estimated_cost = (session_tokens / 1_000_000) * 15.0
            if estimated_cost > MAX_SESSION_COST_USD:
                return self._deny(
                    "budget",
                    f"${estimated_cost:.2f}",
                    f"Presupuesto de sesión excedido: "
                    f"${estimated_cost:.2f} > ${MAX_SESSION_COST_USD}",
                    "HIGH",
                    "budget_exceeded",
                    "Dividir el objetivo en subtareas más pequeñas. "
                    "Iniciar nueva sesión con j --autonomous",
                )
        except Exception:
            pass
        return None


# ── Funciones standalone (usadas por pre_tool_use.py) ───────────────────────


def _notify_telegram_activation(tool_name: str, pattern: str) -> None:
    """Fire-and-forget Telegram alert when a pattern auto-activates at times_seen=3."""
    try:
        import requests
        from dotenv import load_dotenv

        load_dotenv(str(JARVIS_ROOT / ".env"))
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        msg = (
            "🔓 *Auto-aprobación activada*\n"
            f"`{tool_name}` → `{pattern[:80]}`\n"
            "Vistas: 3 veces. Activa para futuros usos."
        )
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception:
        pass  # never block the pipeline


def record_decision(tool: str, inp: dict, result: dict) -> None:
    """
    Registra decisiones APPROVE en la BD.
    Para aprobaciones LOW risk: auto-aprende el patrón en learned_approvals
    cuando se ha visto >= 3 veces (activa el registro).
    """
    if result["decision"] != "APPROVE":
        return
    action_detail = str(inp.get("file_path", inp.get("command", "")))[:200]
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason, risk_level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                action_detail,
                "APPROVE",
                result.get("reason", "OK"),
                result.get("risk_level", "LOW"),
            ),
        )
        # Auto-aprendizaje para patrones de bajo riesgo
        if result.get("risk_level") == "LOW" and result.get("reason") != "learned_approval":
            pattern = action_detail[:50].strip()
            if pattern:
                conn.execute(
                    """
                    INSERT INTO learned_approvals
                        (tool_name, pattern, times_seen, last_seen, active)
                    VALUES (?, ?, 1, datetime('now'), 0)
                    ON CONFLICT(tool_name, pattern) DO UPDATE SET
                        times_seen = times_seen + 1,
                        last_seen  = datetime('now'),
                        active     = CASE WHEN times_seen + 1 >= 3 THEN 1 ELSE 0 END
                    """,
                    (tool, pattern),
                )
                # Notify if this upsert just auto-activated the pattern (times_seen=3)
                row = conn.execute(
                    "SELECT times_seen, active FROM learned_approvals "
                    "WHERE tool_name=? AND pattern=?",
                    (tool, pattern),
                ).fetchone()
                if row and row[0] == 3 and row[1] == 1:
                    _notify_telegram_activation(tool, pattern)
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_rejection(tool: str, inp: dict, result: dict) -> None:
    """
    Registra DENY y ESCALATE en dos canales:
    Canal 1 — BD: tabla permission_decisions
    Canal 2 — JSON buzón: tasks/permission_rejection.json (leído por OrchestratorLoop)
    FIX A: añadido canal JSON.
    """
    if result["decision"] not in ("DENY", "ESCALATE"):
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": SESSION_ID,
        "tool_name": tool,
        "action_detail": str(inp.get("file_path", inp.get("command", "")))[:200],
        "decision": result["decision"],
        "reason": result.get("reason", ""),
        "risk_level": result.get("risk_level", ""),
        "rule_triggered": result.get("rule_triggered", ""),
        "suggested_fix": result.get("suggested_fix", ""),
    }

    # Canal 1: BD
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
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
                entry["action_detail"],
                entry["decision"],
                entry["reason"],
                entry["risk_level"],
                entry["rule_triggered"],
                entry["suggested_fix"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Canal 2: JSON buzón (append al array)
    try:
        reject_path = JARVIS_ROOT / "tasks" / "permission_rejection.json"
        existing: list = []
        if reject_path.exists():
            try:
                existing = json.loads(reject_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.append(entry)
        reject_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
