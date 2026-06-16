#!/usr/bin/env python3
"""Benchmark v3 — Execution Plan Compiler ON vs OFF on Sonnet.

6 agentic-shaped tasks × 2 modes = 12 `claude -p` calls (Sonnet, OAuth, $0).
Scoring per response (0-10):
  - keyword coverage (0-5): task keywords present
  - structure (0-3): numbered steps / phases / verification section present
  - verification discipline (0-2): mentions how to verify done-ness
Same harness philosophy as benchmark_dq.py; deterministic scorer, no LLM judge.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "bin" / "agents"))
from plan_compiler import dq_compile  # noqa: E402

OUT_DIR = ROOT / "tasks" / "benchmarks"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TASKS = [
    {"id": "BC01", "pattern": "debug",
     "prompt": "A Python service crashes with 'sqlite3.OperationalError: database is locked' roughly once an hour under concurrent writers. Describe exactly how you would fix this.",
     "keywords": ["wal", "timeout", "busy", "reproduce", "root cause", "verify", "concurren"]},
    {"id": "BC02", "pattern": "plan",
     "prompt": "Plan the migration of a cron-based scraper fleet to a queue-based architecture without losing scheduled runs.",
     "keywords": ["rollback", "parallel", "cutover", "depend", "risk", "verify", "phase"]},
    {"id": "BC03", "pattern": "optimize",
     "prompt": "An SQL query joining 4 tables takes 10 seconds on SQLite. Walk through optimizing it.",
     "keywords": ["explain query plan", "index", "baseline", "measure", "before", "after"]},
    {"id": "BC04", "pattern": "test",
     "prompt": "Design the test suite for a function that parses European VAT IDs from free text.",
     "keywords": ["edge", "invalid", "happy", "deterministic", "fail", "case"]},
    {"id": "BC05", "pattern": "migrate",
     "prompt": "Migrate a 30 GB MySQL analytics table to PostgreSQL with under 5 minutes of downtime.",
     "keywords": ["count", "checksum", "parity", "dual", "rollback", "cutover", "verify"]},
    {"id": "BC06", "pattern": "deploy",
     "prompt": "Deploy a new systemd-managed Python daemon to a production VPS. Describe your exact procedure.",
     "keywords": ["rollback", "smoke", "health", "monitor", "preflight", "journalctl"]},
]

_STRUCT_PAT = re.compile(r"(^|\n)\s*(\d+[\.\)]|phase|fase|step)", re.I)
_VERIF_PAT = re.compile(r"verif|validate|smoke|check.*(pass|green)|assert", re.I)


def score(text: str, keywords: list) -> dict:
    t = text.lower()
    kw = sum(1 for k in keywords if k in t)
    kw_score = min(5.0, 5.0 * kw / max(1, len(keywords) * 0.6))
    struct = min(3.0, len(_STRUCT_PAT.findall(text)) * 0.5)
    verif = 2.0 if len(_VERIF_PAT.findall(text)) >= 2 else (1.0 if _VERIF_PAT.search(text) else 0.0)
    return {"kw": round(kw_score, 2), "struct": round(struct, 2),
            "verif": verif, "total": round(kw_score + struct + verif, 2)}


def ask_sonnet(prompt: str) -> str:
    env = dict(os.environ, ANTHROPIC_API_KEY="")  # OAuth only — inviolable
    env.pop("CLAUDECODE", None)  # allow nested headless call
    r = subprocess.run(
        ["claude", "-p", prompt, "--model", "sonnet"],
        capture_output=True, text=True, timeout=300, env=env, cwd="/tmp",
    )
    return r.stdout.strip()


def main():
    results = []
    for task in TASKS:
        for mode in ("OFF", "ON"):
            prompt = task["prompt"]
            if mode == "ON":
                prompt = prompt + "\n\n" + dq_compile(prompt, intent_pattern=task["pattern"]).render()
            t0 = time.time()
            try:
                answer = ask_sonnet(prompt)
                s = score(answer, task["keywords"])
            except Exception as exc:
                answer, s = f"ERROR: {exc}", {"kw": 0, "struct": 0, "verif": 0, "total": 0}
            results.append({"task": task["id"], "mode": mode, "score": s,
                            "elapsed_s": round(time.time() - t0, 1),
                            "answer_chars": len(answer)})
            print(f"{task['id']} {mode}: {s['total']}/10 ({round(time.time()-t0,1)}s)", flush=True)
    on = [r["score"]["total"] for r in results if r["mode"] == "ON"]
    off = [r["score"]["total"] for r in results if r["mode"] == "OFF"]
    summary = {"timestamp": datetime.now().isoformat(),
               "model": "sonnet (claude -p, OAuth)",
               "avg_ON": round(sum(on) / len(on), 2),
               "avg_OFF": round(sum(off) / len(off), 2),
               "delta": round(sum(on) / len(on) - sum(off) / len(off), 2),
               "results": results}
    out = OUT_DIR / f"compile_benchmark_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nON {summary['avg_ON']} vs OFF {summary['avg_OFF']} (delta {summary['delta']:+}) → {out}")


if __name__ == "__main__":
    main()
