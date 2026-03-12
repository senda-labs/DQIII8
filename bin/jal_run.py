"""
JAL Run v3 -- orquestador del ciclo completo
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

JARVIS = Path("/root/jarvis")
DB     = JARVIS / "database" / "jarvis_metrics.db"


def get_active_plan() -> tuple:
    conn  = sqlite3.connect(DB)
    row   = conn.execute("""
        SELECT objective_id, current_attempt FROM jal_objectives
        WHERE status='active' ORDER BY started_at DESC LIMIT 1
    """).fetchone()
    if not row:
        conn.close()
        return None, None
    steps = conn.execute("""
        SELECT step_number, description, description
        FROM jal_steps
        WHERE objective_id=? AND attempt=? AND status='pending'
        ORDER BY step_number
    """, (row[0], row[1])).fetchall()
    conn.close()
    return row[0], steps or []


def mark_step(
    obj_id: str,
    attempt: int,
    step_n: int,
    status: str,
    result: str = "",
    error: str = "",
):
    conn = sqlite3.connect(DB)
    conn.execute("""
        UPDATE jal_steps SET status=?, result_summary=?,
            error_raw=?, completed_at=datetime('now')
        WHERE objective_id=? AND attempt=? AND step_number=?
    """, (status, result[:500], error[:500], obj_id, attempt, step_n))
    conn.commit()
    conn.close()


def build_executor_prompt(obj_id: str, attempt: int, steps: list) -> str:
    """
    Construye el prompt para Claude Code.
    Estructurado para minimizar comportamiento no determinista:
    - Instrucciones explicitas y verificables
    - Registro en BD obligatorio por paso
    - Sin decisiones ambiguas
    """
    steps_text = "\n".join(
        f"PASO {s[0]}: {s[1]}\n"
        f"  INSTRUCCION: {s[2] or s[1]}\n"
        f"  REGISTRO: UPDATE jal_steps SET status='completed',"
        f" result_summary='[resultado]' WHERE objective_id='{obj_id}'"
        f" AND attempt={attempt} AND step_number={s[0]};"
        for s in steps
    )

    return f"""Ejecuta los siguientes pasos en orden para el objetivo {obj_id}.

REGLAS ESTRICTAS:
1. Ejecuta cada paso y registra el resultado en BD ANTES de continuar
2. Si un paso falla, registra status='failed' y error_raw='[mensaje]'
3. NO omitas el registro en BD de ningun paso
4. NO tomes decisiones que no esten en las instrucciones
5. Al terminar todos los pasos, ejecuta:
   python3 /root/jarvis/bin/jal_critic.py

PASOS:
{steps_text}

BD: sqlite3 /root/jarvis/database/jarvis_metrics.db "[SQL]"

Empieza por el Paso 1."""


def main():
    # Activar objetivo desde argumento si se pasa
    if len(sys.argv) > 1:
        obj_file = Path(sys.argv[1])
        if obj_file.exists() and obj_file.suffix == ".md":
            target = JARVIS / "objectives" / "active" / obj_file.name
            obj_file.rename(target)
            print(f"[JAL] Activado: {target.name}")

    obj_files = list((JARVIS / "objectives" / "active").glob("*.md"))
    if not obj_files:
        print("[JAL] No hay objetivos en objectives/active/")
        print("[JAL] Uso: python3 bin/jal_run.py objectives/queue/OBJ-001.md")
        sys.exit(0)

    print("[JAL] 1/3 Planificando...")
    subprocess.run(
        ["python3", str(JARVIS / "bin" / "jal_planner.py")],
        cwd=str(JARVIS),
        check=True,
    )

    obj_id, steps = get_active_plan()
    if not obj_id or not steps:
        print("[JAL] No hay pasos pendientes tras la planificacion")
        sys.exit(1)

    print(f"[JAL] 2/3 Ejecutando {len(steps)} pasos con Claude Code...")
    executor_prompt = build_executor_prompt(obj_id, 1, steps)

    prompt_file = JARVIS / "tasks" / "results" / f"jal_exec_{obj_id}.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(executor_prompt, encoding="utf-8")

    # Cargar .env para que OPENROUTER_API_KEY esté disponible en el subproceso
    env_file = JARVIS / ".env"
    env = dict(os.environ)
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())

    subprocess.run(
        ["python3", str(JARVIS / "bin" / "openrouter_wrapper.py"),
         "--model", "qwen/qwen3-coder:free"],
        input=executor_prompt,
        text=True,
        cwd=str(JARVIS),
        env=env,
    )

    print("[JAL] 3/3 Evaluando con Critic...")
    subprocess.run(
        ["python3", str(JARVIS / "bin" / "jal_critic.py")],
        cwd=str(JARVIS),
    )

    print("[JAL] Ciclo completado.")


if __name__ == "__main__":
    main()
