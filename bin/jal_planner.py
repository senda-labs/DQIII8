"""
JAL Planner v3
==============
Descompone objetivos en pasos ejecutables.
Antes de planificar, consulta el historial de fallos de Claude Code
para asignar pesos y criticality basados en datos reales.
"""

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

JARVIS = Path("/root/jarvis")
DB = JARVIS / "database" / "jarvis_metrics.db"

_ALLOWED_HOSTS = frozenset(
    {
        "api.openai.com",
        "openrouter.ai",
        "api.groq.com",
        "api.elevenlabs.io",
        "localhost",
        "127.0.0.1",
    }
)


def _validate_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith(f".{h}") for h in _ALLOWED_HOSTS):
        raise ValueError(f"URL no permitida: {url}")


def load_env():
    env = JARVIS / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_claude_reliability_context() -> str:
    """
    Extrae el historial de fallos de Claude Code desde la BD.
    Este contexto se inyecta en el prompt del planner para que
    asigne mayor criticality a tareas donde Claude falla más.
    """
    try:
        conn = sqlite3.connect(DB)
        patterns = conn.execute("""
            SELECT category, error_signature, failure_rate,
                   avg_severity, prevention_rule
            FROM jal_error_patterns
            WHERE status='active' AND frequency >= 2
            ORDER BY failure_rate DESC
            LIMIT 10
        """).fetchall()
        conn.close()

        if not patterns:
            return "Sin historial de fallos previo."

        lines = ["Patrones de fallo conocidos de Claude Code:"]
        for p in patterns:
            lines.append(
                f"- [{p[0]}] tasa_fallo={p[2]:.0%} "
                f"severidad_media={p[3]:.1f}: {p[1][:80]}"
                + (f" -> PREVENCION: {p[4]}" if p[4] else "")
            )
        return "\n".join(lines)
    except Exception:
        return "BD no disponible para consulta de historial."


def _call_openrouter(prompt: str, model: str = "qwen/qwen3-coder:free") -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[PLANNER] ERROR: OPENROUTER_API_KEY no configurada en .env")
        sys.exit(1)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://jarvis.local",
        "X-Title": "JARVIS",
    }
    fallback_chain = [
        model,
        "stepfun/step-3.5-flash:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]
    for m in fallback_chain:
        payload = json.dumps(
            {
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        _url = "https://openrouter.ai/api/v1/chat/completions"
        _validate_url(_url)
        req = urllib.request.Request(_url, data=payload, headers=headers)
        try:
            _resp = urllib.request.urlopen(req, timeout=120)  # nosemgrep
            with _resp as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            print(f"[PLANNER] {m} -> HTTP {exc.code}, probando fallback...")
            if exc.code not in (429, 500, 502, 503):
                raise
    print("[PLANNER] ERROR: todos los modelos OpenRouter fallaron")
    sys.exit(1)


def plan_with_claude(obj_content: str, reliability_ctx: str) -> list:
    prompt = f"""Eres el planificador de JARVIS, sistema autonomo.

OBJETIVO:
{obj_content}

HISTORIAL DE FIABILIDAD DE CLAUDE CODE (executor):
{reliability_ctx}

Descompone el objetivo en pasos concretos y ejecutables.
Asigna weight y criticality basandote en el historial de fallos:
- Si el historial muestra fallos frecuentes en un tipo de tarea,
  asigna criticality=2 o 3 a ese paso.
- weight debe reflejar la importancia real del paso para el objetivo.
- Los pesos deben sumar exactamente 1.0.

Responde SOLO con JSON valido, sin texto adicional:
{{
    "steps": [
        {{
            "step_number": 1,
            "description": "descripcion clara y ejecutable",
            "weight": 0.0,
            "criticality": 1,
            "executor_instruction": "instruccion exacta para Claude Code",
            "success_criteria": "como verificar que funciono",
            "risk_note": "por que podria fallar segun historial"
        }}
    ],
    "total_weight_check": "suma de weights (debe ser 1.0)",
    "estimated_attempts": 1,
    "plan_rationale": "por que este orden en 1 linea"
}}

LIMITES: minimo 2 pasos, maximo 8 pasos.
CRITICO: criticality=3 solo si el fallo bloquea el objetivo completo."""

    raw = _call_openrouter(prompt)
    for d in ["```json", "```"]:
        if d in raw:
            raw = raw.split(d)[1].split("```")[0]
    return json.loads(raw.strip())["steps"]


def save_plan(obj_id: str, title: str, steps: list, attempt: int):
    conn = sqlite3.connect(DB)
    conn.execute(
        """
        INSERT OR IGNORE INTO jal_objectives
        (objective_id, title, status, started_at)
        VALUES (?, ?, 'active', datetime('now'))
    """,
        (obj_id, title),
    )
    conn.execute(
        """
        UPDATE jal_objectives SET status='active', current_attempt=?
        WHERE objective_id=?
    """,
        (attempt, obj_id),
    )
    for s in steps:
        conn.execute(
            """
            INSERT OR REPLACE INTO jal_steps
            (objective_id, attempt, step_number, description,
             weight, criticality, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
            (obj_id, attempt, s["step_number"], s["description"], s["weight"], s["criticality"]),
        )
    conn.commit()
    conn.close()


def main():
    load_env()
    active_dir = JARVIS / "objectives" / "active"
    obj_files = sorted(active_dir.glob("*.md"))

    if not obj_files:
        print("[PLANNER] No hay objetivos en objectives/active/")
        sys.exit(0)

    obj_path = obj_files[0]
    obj_content = obj_path.read_text(encoding="utf-8")
    obj_id = obj_path.stem

    # Determinar intento actual
    conn = sqlite3.connect(DB)
    row = conn.execute(
        """
        SELECT current_attempt FROM jal_objectives
        WHERE objective_id=?
    """,
        (obj_id,),
    ).fetchone()
    conn.close()
    attempt = (row[0] + 1) if row else 1

    print(f"[PLANNER] Objetivo: {obj_id} | Intento: {attempt}")

    reliability_ctx = get_claude_reliability_context()
    steps = plan_with_claude(obj_content, reliability_ctx)
    save_plan(obj_id, obj_id, steps, attempt)

    print(f"[PLANNER] Plan creado: {len(steps)} pasos")
    for s in steps:
        crit_label = ["", "normal", "importante", "CRITICO"][s["criticality"]]
        print(
            f"  {s['step_number']}. [{crit_label}] w={s['weight']:.2f} "
            f"-- {s['description'][:70]}"
        )

    # Escribir plan en el objetivo
    plan_md = f"\n\n## Plan -- Intento {attempt}\n"
    plan_md += f"_Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
    for s in steps:
        plan_md += f"- [ ] **Paso {s['step_number']}** (w={s['weight']:.2f}, "
        plan_md += f"criticality={s['criticality']}): {s['description']}\n"
        if s.get("risk_note"):
            plan_md += f"  > Riesgo: {s['risk_note']}\n"
    with open(obj_path, "a", encoding="utf-8") as f:
        f.write(plan_md)

    print("[PLANNER] Listo")


if __name__ == "__main__":
    main()
