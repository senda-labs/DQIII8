#!/usr/bin/env python3
"""
DQIII8 — Dispatch Layer (bidirectional bridge CC ↔ routing system)

Permite a Claude Code (sesión interactiva) despachar tareas al sistema de
routing de dqiii8 (NIM/Groq/GitHub/Ollama) con salida estructurada JSON.

Modos de uso:
  Sync:     python3 bin/core/dispatch.py --agent research-analyst --prompt "..."
  Async:    python3 bin/core/dispatch.py --agent python-specialist --prompt "..." --async
  Parallel: python3 bin/core/dispatch.py --tasks tasks.json
  Import:   from bin.core.dispatch import dispatch, dispatch_parallel

Salida JSON:
  {task_id, agent, provider, model, response, tokens_in, tokens_out,
   latency_ms, status, error?, result_file?}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", Path(__file__).resolve().parents[2]))
RESULTS_DIR = DQIII8_ROOT / "tasks" / "results"
WRAPPER = DQIII8_ROOT / "bin" / "core" / "openrouter_wrapper.py"

# Importar routing table para metadata
sys.path.insert(0, str(DQIII8_ROOT))
try:
    from bin.core.openrouter_wrapper import AGENT_ROUTING, _PROVIDER_DEFAULT_MODEL
except ImportError:
    AGENT_ROUTING = {}
    _PROVIDER_DEFAULT_MODEL = {}


def _resolve_agent_meta(agent: str) -> dict:
    """Devuelve provider y model para el agente dado."""
    provider, model = AGENT_ROUTING.get(agent, AGENT_ROUTING.get("default", ("groq", "llama-3.3-70b-versatile")))
    return {"provider": provider, "model": model}


def dispatch(
    agent: str,
    prompt: str,
    context: str = "",
    project: str = "",
    timeout: int = 120,
    async_mode: bool = False,
) -> dict:
    """
    Despacha una tarea al agente indicado vía openrouter_wrapper.

    Returns dict con:
      task_id, agent, provider, model, response, tokens_in, tokens_out,
      latency_ms, status ("ok" | "error" | "timeout"), result_file (si async)
    """
    task_id = str(uuid.uuid4())[:8]
    meta = _resolve_agent_meta(agent)
    full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt
    result_file = RESULTS_DIR / f"dispatch-{task_id}.json"

    if async_mode:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        # Escribe tarea pendiente y lanza en background
        pending = {
            "task_id": task_id, "agent": agent, "status": "pending",
            **meta, "prompt": full_prompt[:200] + "...",
        }
        result_file.write_text(json.dumps(pending, indent=2))
        subprocess.Popen(
            [sys.executable, str(WRAPPER), "--agent", agent, full_prompt],
            stdout=open(str(result_file), "w"),
            stderr=subprocess.DEVNULL,
            cwd=str(DQIII8_ROOT),
        )
        return {"task_id": task_id, "status": "pending", "result_file": str(result_file), **meta}

    # Modo sync — bloquea hasta tener respuesta
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(WRAPPER), "--agent", agent, full_prompt],
            capture_output=True, text=True,
            timeout=timeout,
            cwd=str(DQIII8_ROOT),
        )
        latency_ms = int((time.time() - t0) * 1000)
        response = result.stdout.strip()
        status = "ok" if result.returncode == 0 and response else "error"
        error = result.stderr.strip() if result.returncode != 0 else None

        out = {
            "task_id": task_id,
            "agent": agent,
            "status": status,
            "latency_ms": latency_ms,
            "response": response,
            "error": error,
            **meta,
        }

    except subprocess.TimeoutExpired:
        out = {
            "task_id": task_id, "agent": agent, "status": "timeout",
            "latency_ms": timeout * 1000, "response": "", **meta,
        }

    # Persistir resultado
    if project or async_mode:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps(out, indent=2))
        out["result_file"] = str(result_file)

    return out


def dispatch_parallel(tasks: list[dict], max_workers: int = 6) -> list[dict]:
    """
    Despacha múltiples tareas en paralelo.

    Cada tarea: {agent, prompt, context?, project?, timeout?}
    Returns: lista de resultados en el mismo orden.
    """
    results = [None] * len(tasks)

    def _run(idx: int, task: dict):
        return idx, dispatch(
            agent=task["agent"],
            prompt=task["prompt"],
            context=task.get("context", ""),
            project=task.get("project", ""),
            timeout=task.get("timeout", 120),
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run, i, t): i for i, t in enumerate(tasks)}
        for fut in as_completed(futures):
            idx, result = fut.result()
            results[idx] = result

    return results


def read_result(task_id_or_file: str) -> dict | None:
    """Lee el resultado de una tarea async por task_id o path completo."""
    path = Path(task_id_or_file)
    if not path.exists():
        # buscar por task_id en results dir
        matches = list(RESULTS_DIR.glob(f"dispatch-{task_id_or_file}*.json"))
        if not matches:
            return None
        path = matches[0]
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="DQIII8 Dispatch — despacha tareas al routing system desde CC"
    )
    parser.add_argument("--agent", "-a", default="default", help="Nombre del agente")
    parser.add_argument("--prompt", "-p", help="Prompt de la tarea")
    parser.add_argument("--context", "-c", default="", help="Contexto adicional (texto)")
    parser.add_argument("--context-file", help="Fichero con contexto")
    parser.add_argument("--project", default="", help="Proyecto para persistir resultado")
    parser.add_argument("--timeout", "-t", type=int, default=120)
    parser.add_argument("--async", dest="async_mode", action="store_true",
                        help="Modo async — devuelve task_id inmediatamente")
    parser.add_argument("--tasks", help="JSON file con lista de tareas para dispatch paralelo")
    parser.add_argument("--read", help="Leer resultado de task_id o fichero")
    parser.add_argument("--list-agents", action="store_true", help="Lista agentes disponibles")
    args = parser.parse_args()

    if args.list_agents:
        print("\nAgentes disponibles en AGENT_ROUTING:\n")
        for agent, (prov, model) in sorted(AGENT_ROUTING.items()):
            print(f"  {agent:<28} {prov:<12} {model}")
        return

    if args.read:
        result = read_result(args.read)
        print(json.dumps(result or {"error": "not found"}, indent=2))
        return

    if args.tasks:
        tasks = json.loads(Path(args.tasks).read_text())
        results = dispatch_parallel(tasks)
        print(json.dumps(results, indent=2))
        return

    # Prompt desde args o stdin
    prompt = args.prompt or sys.stdin.read().strip()
    if not prompt:
        parser.error("--prompt o stdin requerido")

    context = args.context
    if args.context_file:
        context = Path(args.context_file).read_text()

    result = dispatch(
        agent=args.agent,
        prompt=prompt,
        context=context,
        project=args.project,
        timeout=args.timeout,
        async_mode=args.async_mode,
    )

    # Output: si es CLI sin pipe → bonito; si hay pipe → JSON puro
    if sys.stdout.isatty() and result.get("status") == "ok":
        print(f"\n[{result['agent']} → {result['provider']}/{result['model']}]")
        print(f"Latency: {result['latency_ms']}ms\n")
        print(result["response"])
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
