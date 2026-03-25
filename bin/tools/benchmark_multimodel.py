#!/usr/bin/env python3
"""
DQIII8 — Multi-Model Benchmark (Fases 1-2)

Fase 1: Run 5 GitHub Models against 20 gold-standard tasks (with/without DQ).
Fase 2: Dual-judge scoring — silver (Gemini 2.5 Flash) + bronze (Groq llama).

Usage:
  python3 bin/tools/benchmark_multimodel.py --run          # Fase 1: collect answers
  python3 bin/tools/benchmark_multimodel.py --score        # Fase 2: judge answers
  python3 bin/tools/benchmark_multimodel.py --report       # Print results table
  python3 bin/tools/benchmark_multimodel.py --run --model deepseek-v3-0324
  python3 bin/tools/benchmark_multimodel.py --run --task FS01

Checkpoint/resume: DB UNIQUE(task_id, model, dq_enabled, run_number) — safe to re-run.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
DB = ROOT / "database" / "dqiii8.db"
NOW_RUN = 1  # bump to re-run a fresh batch

# ── Models under test ────────────────────────────────────────────────────────
MODELS: dict[str, dict] = {
    # GitHub Models (free tier, 60s rate limit)
    "deepseek-v3-0324": {"provider": "github", "strip_think": False, "domains": None},
    "deepseek-r1": {"provider": "github", "strip_think": True, "domains": None},
    "llama-3.3-70b-instruct": {
        "provider": "github",
        "strip_think": False,
        "domains": None,
    },
    "codestral-2501": {"provider": "github", "strip_think": False, "domains": None},
    "gpt-4o-mini": {"provider": "github", "strip_think": False, "domains": None},
    # Ollama local — restricted to applied_sciences (CPU-only VPS, timeouts recorded as data)
    "qwen2.5-coder:7b": {
        "provider": "ollama",
        "strip_think": False,
        "domains": ["applied_sciences"],
    },
    # Groq (30 req/min)
    "llama-3.3-70b-versatile": {
        "provider": "groq",
        "strip_think": False,
        "domains": None,
    },
}

# ── Judges ───────────────────────────────────────────────────────────────────
JUDGE_SILVER = {
    "name": "gemini-2.5-flash",
    "provider": "openrouter",
    "model_id": "google/gemini-2.5-flash-preview",
}
JUDGE_BRONZE = {
    "name": "llama-3.3-70b",
    "provider": "groq",
    "model_id": "llama-3.3-70b-versatile",
}

# ── DQ system prompt (injected when dq_enabled=1) ────────────────────────────
DQ_SYSTEM_PROMPT = (
    "You are an expert assistant with access to a curated knowledge base. "
    "When answering, reason step by step. Be precise, thorough, and cite "
    "specific concepts. Avoid hedging unless genuinely uncertain."
)

GITHUB_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_ENDPOINT = "http://localhost:11434/v1/chat/completions"

# ── Rate limits (seconds between consecutive calls per provider) ─────────────
RATE_LIMITS: dict[str, float] = {
    "github": 60.0,  # 1 req/min free tier
    "openrouter": 4.0,  # ~15 req/min Gemini free tier
    "groq": 2.0,  # 30 req/min
    "ollama": 0.0,  # local, no limit
}

# ── Runs per provider (statistical reliability vs. time budget) ──────────────
RUNS_PER_PROVIDER: dict[str, int] = {
    "github": 3,
    "openrouter": 5,
    "groq": 5,
    "ollama": 5,
}

_last_call_time: dict[str, float] = {}


# ── Utilities ────────────────────────────────────────────────────────────────


def _get_env(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return val


def _throttle(provider: str) -> None:
    """Sleep if needed to respect RATE_LIMITS[provider], then record call time."""
    wait = RATE_LIMITS.get(provider, 0.0)
    if wait <= 0:
        return
    elapsed = time.monotonic() - _last_call_time.get(provider, 0.0)
    if elapsed < wait:
        sleep_for = wait - elapsed
        log.info("Rate limit [%s]: sleeping %.1fs", provider, sleep_for)
        time.sleep(sleep_for)
    _last_call_time[provider] = time.monotonic()


def strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from deepseek-r1 output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _call_api(
    endpoint: str,
    token: str,
    model_id: str,
    messages: list[dict],
    max_tokens: int = 1200,
    timeout: int = 60,
    extra_headers: dict | None = None,
) -> str | None:
    payload = json.dumps(
        {"model": model_id, "messages": messages, "max_tokens": max_tokens}
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body).get("error", {})
            msg = err.get("message", body[:120])
        except Exception:
            msg = body[:120]
        log.warning("HTTP %s calling %s: %s", e.code, endpoint, msg)
        return None
    except Exception as exc:
        log.warning("Request failed (%s): %s", endpoint, exc)
        return None


def call_github_model(
    model_id: str, messages: list[dict], max_tokens: int = 1200
) -> str | None:
    token = _get_env("GITHUB_TOKEN")
    if not token:
        log.error("GITHUB_TOKEN not set")
        return None
    _throttle("github")
    return _call_api(GITHUB_ENDPOINT, token, model_id, messages, max_tokens)


def call_openrouter(
    model_id: str, messages: list[dict], max_tokens: int = 800
) -> str | None:
    token = _get_env("OPENROUTER_API_KEY")
    if not token:
        log.warning("OPENROUTER_API_KEY not set — skipping silver judge")
        return None
    _throttle("openrouter")
    return _call_api(
        OPENROUTER_ENDPOINT,
        token,
        model_id,
        messages,
        max_tokens,
        extra_headers={"HTTP-Referer": "https://jarvis.local", "X-Title": "DQIII8"},
    )


def call_groq(model_id: str, messages: list[dict], max_tokens: int = 800) -> str | None:
    token = _get_env("GROQ_API_KEY")
    if not token:
        log.warning("GROQ_API_KEY not set — skipping bronze judge")
        return None
    _throttle("groq")
    return _call_api(GROQ_ENDPOINT, token, model_id, messages, max_tokens)


def call_ollama(
    model_id: str, messages: list[dict], max_tokens: int = 1200
) -> str | None:
    _throttle("ollama")
    return _call_api(
        OLLAMA_ENDPOINT, "ollama", model_id, messages, max_tokens, timeout=120
    )


def _call_model(model: str, messages: list[dict], max_tokens: int = 1200) -> str | None:
    """Route to the correct provider caller based on MODELS config."""
    provider = MODELS[model]["provider"]
    if provider == "github":
        return call_github_model(model, messages, max_tokens)
    if provider == "ollama":
        return call_ollama(model, messages, max_tokens)
    if provider == "groq":
        return call_groq(model, messages, max_tokens)
    log.error("Unknown provider %r for model %r", provider, model)
    return None


# ── DB helpers ───────────────────────────────────────────────────────────────


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def load_tasks(conn: sqlite3.Connection, task_filter: str | None = None) -> list[dict]:
    sql = "SELECT task_id, domain, prompt, keywords FROM benchmark_gold_standards"
    params: tuple = ()
    if task_filter:
        sql += " WHERE task_id = ?"
        params = (task_filter,)
    sql += " ORDER BY task_id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def load_gold(conn: sqlite3.Connection, task_id: str) -> str:
    row = conn.execute(
        "SELECT gold_answer FROM benchmark_gold_standards WHERE task_id = ?", (task_id,)
    ).fetchone()
    return row["gold_answer"] if row else ""


def already_done(
    conn: sqlite3.Connection, task_id: str, model: str, dq: int, run: int
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM benchmark_multimodel_results "
        "WHERE task_id=? AND model=? AND dq_enabled=? AND run_number=? AND answer IS NOT NULL",
        (task_id, model, dq, run),
    ).fetchone()
    return row is not None


def save_answer(
    conn: sqlite3.Connection,
    task_id: str,
    domain: str,
    model: str,
    dq: int,
    run: int,
    answer_text: str,
    response_time_ms: int,
    enriched_prompt: str | None = None,
    chunks_injected: str | None = None,
    chunk_scores: str | None = None,
) -> None:
    provider = MODELS[model]["provider"]
    conn.execute(
        """INSERT INTO benchmark_multimodel_results
           (task_id, domain, model, provider, dq_enabled, run_number, answer, response_time_ms,
            enriched_prompt, chunks_injected, chunk_scores)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(task_id, model, dq_enabled, run_number) DO UPDATE SET
             answer=excluded.answer,
             response_time_ms=excluded.response_time_ms,
             enriched_prompt=excluded.enriched_prompt,
             chunks_injected=excluded.chunks_injected,
             chunk_scores=excluded.chunk_scores,
             silver_score=NULL, bronze_score=NULL, avg_score=NULL""",
        (
            task_id,
            domain,
            model,
            provider,
            dq,
            run,
            answer_text,
            response_time_ms,
            enriched_prompt,
            chunks_injected,
            chunk_scores,
        ),
    )
    conn.commit()


def save_scores(
    conn: sqlite3.Connection,
    task_id: str,
    model: str,
    dq: int,
    run: int,
    silver_score: float | None,
    bronze_score: float | None,
    keyword_hits: int,
    keyword_total: int,
    silver_raw: str,
    bronze_raw: str,
) -> None:
    avg = None
    scores = [s for s in [silver_score, bronze_score] if s is not None]
    if scores:
        avg = sum(scores) / len(scores)
    conn.execute(
        """UPDATE benchmark_multimodel_results SET
           silver_score=?, bronze_score=?, avg_score=?,
           keyword_hits=?, keyword_total=?,
           silver_judge_raw=?, bronze_judge_raw=?,
           evaluated_at=datetime('now')
           WHERE task_id=? AND model=? AND dq_enabled=? AND run_number=?""",
        (
            silver_score,
            bronze_score,
            avg,
            keyword_hits,
            keyword_total,
            silver_raw[:2000],
            bronze_raw[:2000],
            task_id,
            model,
            dq,
            run,
        ),
    )
    conn.commit()


# ── Fase 1: Collect answers ──────────────────────────────────────────────────

ANSWER_SYSTEM = (
    "Answer the following question thoroughly and accurately. "
    "Be specific — include formulas, mechanisms, or step-by-step reasoning as appropriate."
)

_AGENTS_PATH = str(ROOT / "bin" / "agents")


def _try_enrich(
    prompt: str, domain: str
) -> tuple[str, str | None, str | None, str | None]:
    """Call domain_lens enricher for dq=1 mode.

    Returns (system_prompt, enriched_prompt, chunks_json, scores_json).
    Falls back to DQ_SYSTEM_PROMPT on any error.
    """
    try:
        if _AGENTS_PATH not in sys.path:
            sys.path.insert(0, _AGENTS_PATH)
        from domain_lens import get_domain_lens  # type: ignore
        from knowledge_enricher import get_relevant_chunks  # type: ignore

        lens = get_domain_lens(prompt, domain)
        chunks = get_relevant_chunks(prompt, domain)

        chunks_json = json.dumps(
            [
                {"source": c.get("source", ""), "text": c.get("text", "")[:300]}
                for c in chunks
            ]
        )
        scores_json = json.dumps([round(c.get("score", 0.0), 4) for c in chunks])
        enriched = f"[domain={domain} chunks={len(chunks)}] {prompt}"
        return lens["system_prompt"], enriched, chunks_json, scores_json
    except Exception as exc:
        log.debug("Enrichment unavailable: %s", exc)
        return DQ_SYSTEM_PROMPT, None, None, None


def run_model_on_task(
    task: dict, model: str, dq_enabled: bool, run: int, conn: sqlite3.Connection
) -> None:
    dq = 1 if dq_enabled else 0
    if already_done(conn, task["task_id"], model, dq, run):
        print(f"  [skip] {task['task_id']} {model} dq={dq} run={run} already done")
        return

    enriched_prompt: str | None = None
    chunks_injected: str | None = None
    chunk_scores: str | None = None

    if dq_enabled:
        system, enriched_prompt, chunks_injected, chunk_scores = _try_enrich(
            task["prompt"], task["domain"]
        )
    else:
        system = ANSWER_SYSTEM

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task["prompt"]},
    ]

    print(f"  {task['task_id']} | {model} | dq={dq} run={run} ... ", end="", flush=True)
    t0 = time.monotonic()
    answer = _call_model(model, messages, max_tokens=1200)
    response_time_ms = int((time.monotonic() - t0) * 1000)

    if answer is None:
        error_label = "TIMEOUT" if response_time_ms >= 119000 else "FAILED"
        print(f"{error_label} ({response_time_ms}ms) — saving to DB")
        provider = MODELS[model]["provider"]
        conn.execute(
            """INSERT INTO benchmark_multimodel_results
               (task_id, domain, model, provider, dq_enabled, run_number,
                response_time_ms, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(task_id, model, dq_enabled, run_number) DO UPDATE SET
                 error=excluded.error, response_time_ms=excluded.response_time_ms""",
            (
                task["task_id"],
                task["domain"],
                model,
                provider,
                dq,
                run,
                response_time_ms,
                error_label,
            ),
        )
        conn.commit()
        return

    cfg = MODELS[model]
    if cfg["strip_think"]:
        answer = strip_think(answer)

    save_answer(
        conn,
        task["task_id"],
        task["domain"],
        model,
        dq,
        run,
        answer,
        response_time_ms,
        enriched_prompt,
        chunks_injected,
        chunk_scores,
    )
    print(f"OK ({response_time_ms}ms, {len(answer)} chars)")


def cmd_run(model_filter: str | None, task_filter: str | None) -> None:
    conn = db_connect()
    tasks = load_tasks(conn, task_filter)
    models = [model_filter] if model_filter else list(MODELS.keys())

    total_runs = sum(RUNS_PER_PROVIDER.get(MODELS[m]["provider"], 3) for m in models)
    print(
        f"\n=== Fase 1: Collecting answers — {len(tasks)} tasks × {len(models)} models "
        f"× 2 DQ modes × up to {total_runs // len(models)} runs/model ===\n"
    )
    for task in tasks:
        print(f"[{task['task_id']}] {task['domain']}: {task['prompt'][:60]}...")
        for model in models:
            cfg = MODELS[model]
            allowed = cfg.get("domains")
            if allowed and task["domain"] not in allowed:
                print(
                    f"  SKIP {task['task_id']} | {model} — domain {task['domain']} not in {allowed}"
                )
                continue
            provider = cfg["provider"]
            n_runs = RUNS_PER_PROVIDER.get(provider, 3)
            for run in range(1, n_runs + 1):
                for dq in (False, True):
                    run_model_on_task(task, model, dq, run, conn)
        print()

    conn.close()
    print("Fase 1 complete. Run --score to judge answers.")


# ── Fase 2: Judge answers ────────────────────────────────────────────────────

JUDGE_PROMPT_TEMPLATE = """\
You are an expert evaluator. Score the CANDIDATE ANSWER vs the GOLD ANSWER on a 1-10 scale.

QUESTION:
{prompt}

GOLD ANSWER (authoritative):
{gold}

CANDIDATE ANSWER:
{answer}

Evaluate on:
- Factual accuracy (vs gold)
- Completeness of key concepts
- Reasoning quality
- No hallucinations

Respond in this exact format:
SCORE: <integer 1-10>
REASONING: <2-3 sentences>
"""


def count_keyword_hits(answer: str, keywords_json: str) -> tuple[int, int]:
    try:
        keywords = json.loads(keywords_json) if keywords_json else []
    except Exception:
        keywords = []
    if not keywords:
        return 0, 0
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits, len(keywords)


def parse_score(text: str) -> tuple[float | None, str]:
    m = re.search(r"SCORE:\s*(\d+)", text or "")
    score = float(m.group(1)) if m else None
    m2 = re.search(r"REASONING:\s*(.+)", text or "", re.DOTALL)
    reasoning = m2.group(1).strip()[:500] if m2 else (text or "")[:200]
    return score, reasoning


def score_one(row: dict, conn: sqlite3.Connection) -> None:
    task_id = row["task_id"]
    model = row["model"]
    dq = row["dq_enabled"]
    run = row["run_number"]
    answer = row["answer"]

    task_row = conn.execute(
        "SELECT prompt, gold_answer, keywords FROM benchmark_gold_standards WHERE task_id=?",
        (task_id,),
    ).fetchone()
    if not task_row:
        return

    prompt_text = task_row["prompt"]
    gold = task_row["gold_answer"]
    keywords = task_row["keywords"] or "[]"

    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        prompt=prompt_text, gold=gold[:800], answer=answer[:800]
    )
    messages = [{"role": "user", "content": judge_prompt}]

    print(f"  scoring {task_id} | {model} | dq={dq} ... ", end="", flush=True)

    # Silver judge (Gemini)
    silver_raw = call_openrouter(JUDGE_SILVER["model_id"], messages, max_tokens=300)
    silver_score, silver_reason = parse_score(silver_raw) if silver_raw else (None, "")

    # Bronze judge (Groq llama)
    bronze_raw = call_groq(JUDGE_BRONZE["model_id"], messages, max_tokens=300)
    bronze_score, bronze_reason = parse_score(bronze_raw) if bronze_raw else (None, "")

    kw_hits, kw_total = count_keyword_hits(answer, keywords)

    combined_reason = f"[silver] {silver_reason} | [bronze] {bronze_reason}"
    save_scores(
        conn,
        task_id,
        model,
        dq,
        run,
        silver_score,
        bronze_score,
        kw_hits,
        kw_total,
        combined_reason,
    )

    scores_str = f"silver={silver_score} bronze={bronze_score} kw={kw_hits}/{kw_total}"
    print(f"OK — {scores_str}")


def cmd_score(model_filter: str | None, task_filter: str | None) -> None:
    conn = db_connect()
    sql = (
        "SELECT task_id, model, dq_enabled, run_number, answer "
        "FROM benchmark_multimodel_results "
        "WHERE silver_score IS NULL AND answer IS NOT NULL"
    )
    params: list = []
    if model_filter:
        sql += " AND model=?"
        params.append(model_filter)
    if task_filter:
        sql += " AND task_id=?"
        params.append(task_filter)
    sql += " ORDER BY task_id, model, dq_enabled"

    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    print(f"\n=== Fase 2: Scoring {len(rows)} unscored answers ===\n")
    for row in rows:
        score_one(row, conn)
    conn.close()
    print("\nFase 2 complete. Run --report to see results.")


# ── Report ───────────────────────────────────────────────────────────────────


def cmd_report(model_filter: str | None) -> None:
    conn = db_connect()
    sql = """
        SELECT model, dq_enabled,
               COUNT(*) as n,
               ROUND(AVG(avg_score), 2) as avg_score,
               ROUND(AVG(silver_score), 2) as avg_silver,
               ROUND(AVG(bronze_score), 2) as avg_bronze,
               ROUND(AVG(CAST(keyword_hits AS REAL) / NULLIF(keyword_total, 0)), 3) as kw_rate,
               ROUND(AVG(response_time_ms), 0) as avg_ms
        FROM benchmark_multimodel_results
        WHERE silver_score IS NOT NULL AND run_number=?
    """
    params: list = [NOW_RUN]
    if model_filter:
        sql += " AND model=?"
        params.append(model_filter)
    sql += " GROUP BY model, dq_enabled ORDER BY avg_score DESC NULLS LAST"

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if not rows:
        print("No scored results found. Run --run then --score first.")
        return

    print(f"\n=== Benchmark Report — run #{NOW_RUN} ===\n")
    hdr = f"{'Model':<30} {'DQ':>3} {'N':>4} {'Avg':>5} {'Silver':>7} {'Bronze':>7} {'KW%':>6} {'ms':>7}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        dq_flag = "yes" if r["dq_enabled"] else "no"
        avg = f"{r['avg_score']:.2f}" if r["avg_score"] is not None else "  N/A"
        sil = f"{r['avg_silver']:.2f}" if r["avg_silver"] is not None else "  N/A"
        bro = f"{r['avg_bronze']:.2f}" if r["avg_bronze"] is not None else "  N/A"
        kw = f"{r['kw_rate']*100:.1f}%" if r["kw_rate"] is not None else "  N/A"
        ms = f"{int(r['avg_ms'])}" if r["avg_ms"] is not None else "  N/A"
        print(
            f"{r['model']:<30} {dq_flag:>3} {r['n']:>4} {avg:>5} {sil:>7} {bro:>7} {kw:>6} {ms:>7}"
        )
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="DQIII8 Multi-Model Benchmark")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--run", action="store_true", help="Fase 1: collect model answers"
    )
    group.add_argument(
        "--score", action="store_true", help="Fase 2: judge answers with dual judges"
    )
    group.add_argument("--report", action="store_true", help="Print results table")
    parser.add_argument("--model", default=None, help="Filter to one model")
    parser.add_argument(
        "--task", default=None, help="Filter to one task_id (e.g. FS01)"
    )
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        sys.exit(1)

    if args.run:
        cmd_run(args.model, args.task)
    elif args.score:
        cmd_score(args.model, args.task)
    elif args.report:
        cmd_report(args.model)


if __name__ == "__main__":
    main()
