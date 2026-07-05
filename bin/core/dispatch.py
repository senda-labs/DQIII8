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

Async (fixed 2026-07-05 — audit CRITICAL #1): the parent writes a "pending" JSON
envelope to tasks/results/dispatch-<id>.json and spawns a DETACHED WORKER
(this same script with --_worker) that runs the normal sync path, then
atomically replaces the envelope with the final JSON result. read_result()
therefore always sees valid JSON: {"status": "pending"} until completion,
then {"status": "ok"|"error"|"timeout", "response": ...}.
(The old design piped raw wrapper stdout over the .json file — unparseable.)

Salida JSON:
  {task_id, agent, provider, model, response, latency_ms, status,
   error?, result_file?}
  (tokens_in/tokens_out no se emiten — el wrapper no los expone vía stdout.)
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


def _load_dotenv() -> None:
    """Load .env into os.environ so subprocess inherits API keys."""
    env_file = DQIII8_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

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


# Optional Agno backend for OpenAI-compatible providers (NIM/Groq/GitHub).
# Opt-in via DQIII8_USE_AGNO=1 to preserve the default subprocess behaviour
# that CC skills depend on. Subprocess remains the fallback on any failure.
try:
    from bin.core.agno_agents import AgentRegistry as _AgentRegistry

    _AGNO_REGISTRY = _AgentRegistry()
    _USE_AGNO = True
except Exception:
    _AGNO_REGISTRY = None
    _USE_AGNO = False

_AGNO_FALLBACK_PROVIDERS = {"ollama", "anthropic"}


def _agno_enabled() -> bool:
    return _USE_AGNO and os.environ.get("DQIII8_USE_AGNO") == "1"


# Default sync timeout. NOTE (audit 2026-07-05 MED: timeout inversion): the
# wrapper's per-attempt HTTP timeout is 180s and the claude CLI path allows
# 300s — a 120s outer timeout killed slow-but-succeeding Tier-A calls while the
# wrapper logged success (double-execution risk). Keep this ≥ 300.
DEFAULT_TIMEOUT = 300


def dispatch(
    agent: str,
    prompt: str,
    context: str = "",
    project: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    async_mode: bool = False,
) -> dict:
    """
    Despacha una tarea al agente indicado vía openrouter_wrapper.

    Returns dict con:
      task_id, agent, provider, model, response, latency_ms,
      status ("ok" | "error" | "timeout" | "pending"), result_file (si async)
    """
    task_id = str(uuid.uuid4())[:8]
    meta = _resolve_agent_meta(agent)
    full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt
    result_file = RESULTS_DIR / f"dispatch-{task_id}.json"

    if async_mode:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        # Persist the prompt for the worker (may exceed argv limits) and write
        # a valid "pending" JSON envelope that the worker atomically replaces.
        prompt_file = RESULTS_DIR / f"dispatch-{task_id}.prompt"
        prompt_file.write_text(full_prompt)
        pending = {
            "task_id": task_id, "agent": agent, "status": "pending",
            **meta, "prompt": full_prompt[:200],
            "result_file": str(result_file),
        }
        result_file.write_text(json.dumps(pending, indent=2))
        try:
            subprocess.Popen(
                [
                    sys.executable, str(Path(__file__).resolve()), "--_worker",
                    "--agent", agent,
                    "--_prompt-file", str(prompt_file),
                    "--_result-file", str(result_file),
                    "--_task-id", task_id,
                    "--timeout", str(timeout),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(DQIII8_ROOT),
                start_new_session=True,  # survive parent exit
            )
        except Exception as exc:
            failed = {**pending, "status": "error", "error": f"worker spawn failed: {exc}"}
            result_file.write_text(json.dumps(failed, indent=2))
            return failed
        return {"task_id": task_id, "status": "pending", "result_file": str(result_file), **meta}

    # Modo sync — Agno backend opcional (NIM/Groq/GitHub) si está habilitado
    if _agno_enabled() and meta["provider"] not in _AGNO_FALLBACK_PROVIDERS:
        try:
            agno_res = _AGNO_REGISTRY.run(agent, full_prompt, timeout=timeout)
            if agno_res.get("status") == "ok" and agno_res.get("response"):
                out = {
                    "task_id": task_id,
                    "agent": agent,
                    "status": "ok",
                    "latency_ms": agno_res.get("latency_ms", 0),
                    "response": agno_res.get("response", ""),
                    "error": None,
                    **meta,
                }
                if project or async_mode:
                    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                    result_file.write_text(json.dumps(out, indent=2))
                    out["result_file"] = str(result_file)
                return out
        except Exception:
            pass  # fall through to subprocess

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
            timeout=task.get("timeout", DEFAULT_TIMEOUT),
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run, i, t): i for i, t in enumerate(tasks)}
        for fut in as_completed(futures):
            idx, result = fut.result()
            results[idx] = result

    return results


def _run_async_worker(
    agent: str, prompt_file: str, result_file: str, task_id: str, timeout: int
) -> None:
    """Detached async worker: run the sync path and atomically publish the result.

    Always leaves valid JSON in result_file (tmp-write + os.replace), even on
    crash — read_result() can never observe a half-written or raw-text file.
    """
    rf = Path(result_file)
    try:
        prompt = Path(prompt_file).read_text()
        out = dispatch(agent=agent, prompt=prompt, timeout=timeout, async_mode=False)
        out["task_id"] = task_id
        out["result_file"] = str(rf)
    except Exception as exc:
        out = {
            "task_id": task_id, "agent": agent, "status": "error",
            "response": "", "error": f"async worker crashed: {exc}",
            "result_file": str(rf),
        }
    tmp = rf.with_name(rf.name + ".tmp")
    tmp.write_text(json.dumps(out, indent=2))
    os.replace(tmp, rf)
    try:
        Path(prompt_file).unlink()
    except OSError:
        pass


def read_result(task_id_or_file: str) -> dict | None:
    """Lee el resultado de una tarea async por task_id o path completo.

    Devuelve {"status": "pending", ...} mientras el worker no ha terminado;
    después, el resultado final. None solo si la tarea no existe."""
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


def run_code_quality(spec: str, context: str = "", city_block_name: str = "") -> dict:
    """
    Run the full MetaGPT city-block pipeline from the dispatch layer.

    Returns CodeQualityResult as a dict.
    """
    from bin.core.code_quality import CodeQualityPipeline

    result = CodeQualityPipeline().run(
        spec=spec, context=context, city_block_name=city_block_name
    )
    return result.__dict__


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
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--async", dest="async_mode", action="store_true",
                        help="Modo async — devuelve task_id inmediatamente")
    parser.add_argument("--tasks", help="JSON file con lista de tareas para dispatch paralelo")
    parser.add_argument("--read", help="Leer resultado de task_id o fichero")
    parser.add_argument("--list-agents", action="store_true", help="Lista agentes disponibles")
    # Internal async-worker plumbing (spawned by dispatch(async_mode=True))
    parser.add_argument("--_worker", dest="_worker", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--_prompt-file", dest="_prompt_file", help=argparse.SUPPRESS)
    parser.add_argument("--_result-file", dest="_result_file", help=argparse.SUPPRESS)
    parser.add_argument("--_task-id", dest="_task_id", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args._worker:
        _run_async_worker(
            agent=args.agent,
            prompt_file=args._prompt_file,
            result_file=args._result_file,
            task_id=args._task_id,
            timeout=args.timeout,
        )
        return

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
