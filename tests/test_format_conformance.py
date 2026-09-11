"""tests/test_format_conformance.py — el repo cumple su propia config de formato.

Por que existe: black corre en un PostToolUse hook, o sea solo sobre ficheros que
alguien edita. Un fichero que nadie toca puede quedar fuera de `pyproject.toml`
indefinidamente sin que nada avise — y asi llegaron 134 ficheros a divergir
(2026-08-20). El hook cierra el flujo nuevo; este test cierra el acumulado.

El fallo se lista por fichero, no como un booleano, para que se vea el alcance sin
tener que reproducir el comando a mano.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _non_conformant() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "black", "--check", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return sorted(
        ln.split("would reformat ", 1)[1].strip().replace(f"{ROOT}/", "")
        for ln in (proc.stderr + proc.stdout).splitlines()
        if ln.startswith("would reformat ")
    )


def test_repo_matches_its_own_black_config():
    offenders = _non_conformant()
    assert not offenders, (
        f"{len(offenders)} fichero(s) fuera de [tool.black] en pyproject.toml.\n"
        "Los de .claude/ son gobernanza (ESCALATE): los aplica un humano.\n"
        + "\n".join(f"  {o}" for o in offenders)
    )
