#!/usr/bin/env python3
"""DQIII8 Benchmark — Dual Gold Standard vs Vanilla vs Enriched.

Measures:
1. Gold Standard Gap: distance from Sonnet 4.6 (gold) or Gemini 2.5 Flash (silver)
2. Hallucination Index: variance in vanilla model across 5 runs
3. DQ Enricher Value: improvement with pipeline ON vs OFF

20 tasks x 5 queries x 2 modes (ON/OFF) x 1 model = 200 LLM calls
Plus 20 Gemini calls (silver standard, always available)
Plus up to 20 Sonnet calls (gold standard, only in Claude Code session)
Plus evaluation calls
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = DQIII8_ROOT / "database" / "jarvis_metrics.db"
WRAPPER = DQIII8_ROOT / "bin" / "core" / "openrouter_wrapper.py"
RESULTS_DIR = DQIII8_ROOT / "tasks" / "benchmarks"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Load .env
_env_path = DQIII8_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# 20 TASKS — one per domain/centroid
TASKS = [
    # formal_sciences (4 tasks)
    {
        "id": "FS01",
        "domain": "formal_sciences",
        "prompt": "Explain the Kelly Criterion for optimal bet sizing. Include the mathematical formula, derive it from first principles, and give a practical example with a coinflip that has 60% win probability and 2:1 payout.",
        "keywords": ["kelly", "f*", "bankroll", "edge", "odds"],
    },
    {
        "id": "FS02",
        "domain": "formal_sciences",
        "prompt": "What is the difference between Bayesian and Frequentist approaches to probability? Give a concrete example where they give different answers and explain why.",
        "keywords": ["prior", "posterior", "likelihood", "confidence", "credible"],
    },
    {
        "id": "FS03",
        "domain": "formal_sciences",
        "prompt": "Explain Big O notation with examples of O(1), O(log n), O(n), O(n log n), O(n^2), and O(2^n). For each, give a real algorithm that has that complexity.",
        "keywords": ["constant", "logarithmic", "linear", "quadratic", "exponential"],
    },
    {
        "id": "FS04",
        "domain": "formal_sciences",
        "prompt": "Derive the Black-Scholes option pricing formula step by step. Explain each variable and give a numerical example pricing a European call option.",
        "keywords": ["volatility", "strike", "expiry", "d1", "d2", "N(d)"],
    },
    # natural_sciences (4 tasks)
    {
        "id": "NS01",
        "domain": "natural_sciences",
        "prompt": "Explain the Katch-McArdle BMR formula. How does it differ from Mifflin-St Jeor? Calculate BMR for a 75kg male with 15% body fat using both formulas.",
        "keywords": ["lean mass", "BMR", "kcal", "body fat", "metabolic"],
    },
    {
        "id": "NS02",
        "domain": "natural_sciences",
        "prompt": "How does mRNA vaccine technology work? Explain the full pathway from injection to immune response, including the role of lipid nanoparticles, ribosome translation, and T-cell activation.",
        "keywords": ["spike protein", "ribosome", "lipid", "antibody", "T-cell"],
    },
    {
        "id": "NS03",
        "domain": "natural_sciences",
        "prompt": "Explain CRISPR-Cas9 gene editing. How does the guide RNA find its target? What are off-target effects and how are they minimized?",
        "keywords": ["Cas9", "guide RNA", "PAM", "double-strand break", "repair"],
    },
    {
        "id": "NS04",
        "domain": "natural_sciences",
        "prompt": "Explain the protein folding problem. What did AlphaFold solve and what remains unsolved? How does the attention mechanism in the model capture co-evolutionary information?",
        "keywords": ["tertiary structure", "MSA", "attention", "CASP", "Evoformer"],
    },
    # social_sciences (4 tasks)
    {
        "id": "SS01",
        "domain": "social_sciences",
        "prompt": "Calculate WACC for a company with: 60% equity at 12% cost, 40% debt at 6% pre-tax cost, 25% tax rate. Then explain how WACC changes if the company increases leverage to 50/50.",
        "keywords": [
            "WACC",
            "cost of equity",
            "cost of debt",
            "tax shield",
            "Modigliani",
        ],
    },
    {
        "id": "SS02",
        "domain": "social_sciences",
        "prompt": "Explain Porter's Five Forces framework. Apply it to analyze the competitive landscape of the cloud computing industry (AWS, Azure, GCP).",
        "keywords": [
            "barriers to entry",
            "supplier power",
            "buyer power",
            "substitutes",
            "rivalry",
        ],
    },
    {
        "id": "SS03",
        "domain": "social_sciences",
        "prompt": "What is the difference between fiscal and monetary policy? How did the US Federal Reserve and Treasury respond differently to the 2020 COVID recession vs the 2008 financial crisis?",
        "keywords": [
            "interest rate",
            "quantitative easing",
            "stimulus",
            "deficit",
            "inflation",
        ],
    },
    {
        "id": "SS04",
        "domain": "social_sciences",
        "prompt": "Explain the CAP theorem in distributed systems. Give examples of databases that choose CP (consistency+partition tolerance) vs AP (availability+partition tolerance) and why.",
        "keywords": [
            "consistency",
            "availability",
            "partition",
            "eventual",
            "linearizable",
        ],
    },
    # humanities_arts (4 tasks)
    {
        "id": "HA01",
        "domain": "humanities_arts",
        "prompt": "Compare Stoic and Epicurean philosophy. How do they differ on the role of pleasure, virtue, and the good life? Which is more applicable to modern tech entrepreneurship?",
        "keywords": ["Seneca", "Epicurus", "ataraxia", "virtue", "pleasure"],
    },
    {
        "id": "HA02",
        "domain": "humanities_arts",
        "prompt": "Explain the principles of Bauhaus design. How did it influence modern UI/UX design? Give specific examples of Bauhaus principles visible in today's digital products.",
        "keywords": [
            "form follows function",
            "Gropius",
            "grid",
            "minimalism",
            "typography",
        ],
    },
    {
        "id": "HA03",
        "domain": "humanities_arts",
        "prompt": "What is the Sapir-Whorf hypothesis? Does language shape thought or reflect it? Give examples from at least 3 languages where linguistic structure correlates with different cognitive patterns.",
        "keywords": [
            "linguistic relativity",
            "Sapir",
            "Whorf",
            "color perception",
            "spatial",
        ],
    },
    {
        "id": "HA04",
        "domain": "humanities_arts",
        "prompt": "Analyze the narrative structure of Christopher Nolan's films. How does non-linear storytelling in Memento, Inception, and Tenet create meaning through temporal manipulation?",
        "keywords": ["non-linear", "exposition", "reverse", "temporal", "paradox"],
    },
    # applied_sciences (4 tasks)
    {
        "id": "AS01",
        "domain": "applied_sciences",
        "prompt": "Explain RAG (Retrieval Augmented Generation) architecture. What are the key components (embedding, vector store, retrieval, generation)? What are common failure modes and how to fix them?",
        "keywords": [
            "embedding",
            "cosine similarity",
            "chunk",
            "hallucination",
            "reranking",
        ],
    },
    {
        "id": "AS02",
        "domain": "applied_sciences",
        "prompt": "Design a multi-model routing system that sends prompts to the cheapest capable model. What signals would you use to classify prompt complexity? How would you handle fallback and quality verification?",
        "keywords": ["routing", "classification", "fallback", "cost", "quality gate"],
    },
    {
        "id": "AS03",
        "domain": "applied_sciences",
        "prompt": "Explain the MCP (Model Context Protocol) specification. What problems does it solve? How does a MCP server expose tools to an LLM client? Give an example of building a simple MCP server.",
        "keywords": ["tools", "resources", "stdio", "transport", "schema"],
    },
    {
        "id": "AS04",
        "domain": "applied_sciences",
        "prompt": "Compare fine-tuning vs RAG vs prompt engineering for customizing LLM behavior. When should you use each? What are the cost/quality/latency tradeoffs?",
        "keywords": [
            "fine-tune",
            "retrieval",
            "prompt",
            "latency",
            "cost",
            "context window",
        ],
    },
]

RUBRIC = """Score this response against the Gold Standard on 5 dimensions (1-10 each):

1. ACCURACY: Are the facts, formulas, and examples correct?
2. COMPLETENESS: Does it cover all key points the Gold Standard covers?
3. DEPTH: Is the explanation as detailed and nuanced as the Gold Standard?
4. CLARITY: Is it well-structured and easy to follow?
5. ACTIONABILITY: Can someone use this response to take action or apply the knowledge?

Also assess:
- HALLUCINATION_DETECTED: yes/no — Did it state something factually wrong with confidence?
- MISSING_KEY_CONCEPTS: list of concepts in Gold Standard but missing here
- EXTRA_VALUE: anything this response has that the Gold Standard doesn't
- ENRICHER_IMPACT: positive/negative/neutral — did the DQ enricher help or hurt?

Respond ONLY with JSON:
{
  "accuracy": N,
  "completeness": N,
  "depth": N,
  "clarity": N,
  "actionability": N,
  "total": N,
  "hallucination_detected": "yes/no",
  "missing_key_concepts": ["concept1", "concept2"],
  "extra_value": "description or empty string",
  "enricher_impact": "positive/negative/neutral"
}"""


def call_model(prompt: str, use_dq: bool = False, agent: str = "default") -> str:
    """Call a model via DQ pipeline (DQ ON) or directly (DQ OFF)."""
    cmd = ["python3", str(WRAPPER), "--agent", agent]
    if not use_dq:
        cmd.append("--no-enrich")
    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(DQIII8_ROOT),
        )
        return result.stdout.strip()[:3000]
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as exc:
        log.warning("call_model: %s", exc)
        return f"[ERROR: {exc}]"


def call_gemini(prompt: str) -> str:
    """Call Gemini 2.5 Flash as silver standard (free, always available)."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return "[NO_GEMINI_KEY]"
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={api_key}"
        )
        data = json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 2000},
            }
        ).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        response = urllib.request.urlopen(req, timeout=90)
        result = json.loads(response.read())
        return result["candidates"][0]["content"]["parts"][0]["text"][:3000]
    except Exception as e:
        print(f"  [SILVER] Gemini error: {e}")
        return "[GEMINI_ERROR]"


def call_sonnet(prompt: str) -> str | None:
    """Call Sonnet 4.6 as gold standard (only works within Claude Code session).

    Returns None if not available — do not fallback, caller decides.
    """
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(DQIII8_ROOT),
        )
        output = result.stdout.strip()
        if output and len(output) > 20 and "error" not in output.lower()[:50]:
            return output[:3000]
    except Exception:
        pass
    return None


def evaluate(gold: str, response: str, task: dict, mode: str) -> dict:
    """Evaluate response against gold standard using Groq (DQ OFF — no enrichment bias)."""
    eval_prompt = (
        f"You are an expert evaluator. Compare this response to the Gold Standard.\n\n"
        f"TASK: {task['prompt'][:200]}\n"
        f"DOMAIN: {task['domain']}\n"
        f"EXPECTED KEYWORDS: {', '.join(task['keywords'])}\n\n"
        f"GOLD STANDARD:\n{gold[:1500]}\n\n"
        f"RESPONSE TO EVALUATE ({mode}):\n{response[:1500]}\n\n"
        f"{RUBRIC}"
    )
    raw = call_model(eval_prompt, use_dq=False, agent="default")
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception as exc:
        log.warning("evaluate parse failed: %s", exc)
    return {"total": 0, "error": "parse_failed", "raw": raw[:200]}


def update_enricher_feedback(task: dict, score: dict) -> None:
    """Feed back to the enricher what worked and what didn't."""
    missing = score.get("missing_key_concepts", [])
    if not missing:
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """INSERT INTO knowledge_usage
                   (query, domain, chunks_used, chunks_relevant, feedback)
                   VALUES (?, ?, 0, 0, ?)""",
                (
                    task["prompt"][:200],
                    task["domain"],
                    json.dumps(
                        {
                            "benchmark": True,
                            "missing_concepts": missing,
                            "enricher_impact": score.get("enricher_impact", "neutral"),
                            "score": score.get("total", 0),
                        }
                    ),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.warning("update_enricher_feedback: %s", exc)


def generate_and_send_report(results: dict, report_path: Path) -> None:
    """Generate markdown report and send via Telegram."""
    timestamp = results["metadata"]["timestamp"]

    sonnet_available = results["metadata"].get("sonnet_available_tasks", "?")
    n_tasks = len(results["tasks"])

    lines = [
        f"# DQ Benchmark Report — {timestamp}",
        "",
        "## Configuracion",
        f"- Tareas: {n_tasks}",
        "- Queries por tarea: 5",
        "- Silver Standard: Gemini 2.5 Flash",
        f"- Gold Standard: Sonnet 4.6 (available: {sonnet_available}/{n_tasks} tasks)",
        "- Modelos evaluados: Groq llama-3.3-70b",
        "",
        "## Resultados por Tarea",
        "",
        "| Task | Domain | DQ OFF | DQ ON | Delta | Halluc | Enricher |",
        "|------|--------|--------|-------|-------|--------|----------|",
    ]

    total_off: list[float] = []
    total_on: list[float] = []
    total_halluc = 0
    positive_enricher = 0
    negative_enricher = 0

    for task in results["tasks"]:
        scores_off: list[float] = []
        scores_on: list[float] = []
        halluc = 0

        for run in task["runs"]:
            for model, data in run.get("models", {}).items():
                if model == "ollama":
                    continue
                if "dq_off" in data and isinstance(data["dq_off"].get("score"), dict):
                    s = data["dq_off"]["score"].get("total", 0)
                    if isinstance(s, (int, float)):
                        scores_off.append(s)
                    if data["dq_off"].get("hallucination") == "yes":
                        halluc += 1
                if "dq_on" in data and isinstance(data["dq_on"].get("score"), dict):
                    s = data["dq_on"]["score"].get("total", 0)
                    if isinstance(s, (int, float)):
                        scores_on.append(s)

        avg_off = sum(scores_off) / len(scores_off) if scores_off else 0.0
        avg_on = sum(scores_on) / len(scores_on) if scores_on else 0.0
        delta = avg_on - avg_off
        impact = "OK" if delta > 2 else "-" if delta > -2 else "X"

        if delta > 2:
            positive_enricher += 1
        elif delta < -2:
            negative_enricher += 1

        total_off.append(avg_off)
        total_on.append(avg_on)
        total_halluc += halluc

        lines.append(
            f"| {task['id']} | {task['domain'][:12]} | "
            f"{avg_off:.1f}/50 | {avg_on:.1f}/50 | "
            f"{'+' if delta >= 0 else ''}{delta:.1f} | "
            f"{halluc}/5 | {impact} |"
        )

    global_off = sum(total_off) / len(total_off) if total_off else 0.0
    global_on = sum(total_on) / len(total_on) if total_on else 0.0
    global_delta = global_on - global_off

    lines.extend(
        [
            "",
            "## Resumen Global",
            "",
            f"- DQ OFF promedio: {global_off:.1f}/50",
            f"- DQ ON promedio: {global_on:.1f}/50",
            f"- Delta global: {'+' if global_delta >= 0 else ''}{global_delta:.1f} puntos",
            f"- Hallucinations totales: {total_halluc}/{n_tasks * 5}",
            f"- Enricher positivo: {positive_enricher}/{n_tasks} tareas",
            f"- Enricher negativo: {negative_enricher}/{n_tasks} tareas",
            "",
            "## Interpretacion",
            "",
        ]
    )

    if global_delta > 5:
        lines.append("VERDE: DQ mejora significativamente los modelos gratis.")
    elif global_delta > 0:
        lines.append("AMARILLO: DQ mejora ligeramente los modelos gratis.")
    else:
        lines.append(
            "ROJO: DQ no mejora los modelos gratis. Revisar enricher pipeline."
        )

    halluc_ratio = total_halluc / (n_tasks * 5) if n_tasks else 0
    lines.extend(
        [
            "",
            "## Hallucination Index",
            "",
            f"- Ratio: {total_halluc}/{n_tasks * 5} ({halluc_ratio * 100:.0f}%)",
        ]
    )
    if total_halluc > n_tasks * 2:
        lines.append("AVISO: Alto ratio de alucinacion.")
    else:
        lines.append("OK: Ratio de alucinacion aceptable.")

    lines.extend(["", "## Dominios donde DQ mas aporta", ""])
    domain_deltas: dict[str, list[float]] = {}
    for task, off, on in zip(results["tasks"], total_off, total_on):
        d = task["domain"]
        domain_deltas.setdefault(d, []).append(on - off)

    for domain, deltas in sorted(
        domain_deltas.items(), key=lambda x: -(sum(x[1]) / len(x[1]))
    ):
        avg_d = sum(deltas) / len(deltas)
        tag = "VERDE" if avg_d > 2 else "AMARILLO" if avg_d > -2 else "ROJO"
        lines.append(f"- {tag} {domain}: {'+' if avg_d >= 0 else ''}{avg_d:.1f} puntos")

    lines.extend(
        [
            "",
            "---",
            "Generado automaticamente por DQIII8 Benchmark System",
            f"Reporte completo: {report_path}",
        ]
    )

    report_md = "\n".join(lines)

    md_path = RESULTS_DIR / f"benchmark_report_{timestamp}.md"
    md_path.write_text(report_md, encoding="utf-8")
    print(f"[REPORT] Saved: {md_path}")

    bot_token = os.environ.get(
        "TELEGRAM_BOT_TOKEN", os.environ.get("DQIII8_BOT_TOKEN", "")
    )
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if bot_token and chat_id:
        chunks = [report_md[i : i + 4000] for i in range(0, len(report_md), 4000)]
        for chunk in chunks:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps(
                {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
            ).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                urllib.request.urlopen(req, timeout=10)
            except Exception as exc:
                log.warning("Telegram send failed: %s", exc)
            time.sleep(1)
        print("[TELEGRAM] Report sent")
    else:
        print("[TELEGRAM] No bot token/chat_id — report saved locally only")


def print_summary(results: dict) -> None:
    """Print summary statistics to stdout."""
    print(f"\n{'='*60}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*60}")

    for task in results["tasks"]:
        scores_off: list[float] = []
        scores_on: list[float] = []
        hallucinations = 0

        for run in task["runs"]:
            for model, data in run.get("models", {}).items():
                if model == "ollama":
                    continue
                if "dq_off" in data and isinstance(data["dq_off"].get("score"), dict):
                    s = data["dq_off"]["score"].get("total", 0)
                    if isinstance(s, (int, float)):
                        scores_off.append(s)
                    if data["dq_off"].get("hallucination") == "yes":
                        hallucinations += 1
                if "dq_on" in data and isinstance(data["dq_on"].get("score"), dict):
                    s = data["dq_on"]["score"].get("total", 0)
                    if isinstance(s, (int, float)):
                        scores_on.append(s)

        avg_off = sum(scores_off) / len(scores_off) if scores_off else 0.0
        avg_on = sum(scores_on) / len(scores_on) if scores_on else 0.0
        variance_off = (
            sum((s - avg_off) ** 2 for s in scores_off) / len(scores_off)
            if len(scores_off) > 1
            else 0.0
        )
        delta = avg_on - avg_off
        print(f"\n{task['id']} ({task['domain']}):")
        print(
            f"  DQ OFF avg: {avg_off:.1f}/50 | variance: {variance_off:.1f}"
            f" | hallucinations: {hallucinations}"
        )
        print(
            f"  DQ ON  avg: {avg_on:.1f}/50 | delta:"
            f" {'+' if delta >= 0 else ''}{delta:.1f}"
        )
        impact = "POSITIVE" if delta > 2 else "NEUTRAL" if delta > -2 else "NEGATIVE"
        print(f"  Enricher impact: {impact}")


def run_benchmark() -> None:
    """Run the complete benchmark."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = RESULTS_DIR / f"benchmark_{timestamp}.json"

    results: dict = {
        "metadata": {
            "timestamp": timestamp,
            "tasks": len(TASKS),
            "queries_per_task": 5,
            "models": ["groq_llama-3.3-70b"],
            "gold_standard": "claude-sonnet-4-20250514 (when available)",
            "silver_standard": "gemini-2.5-flash (always available)",
        },
        "tasks": [],
    }

    total_tasks = len(TASKS)

    for i, task in enumerate(TASKS):
        print(f"\n{'='*60}")
        print(f"TASK {i + 1}/{total_tasks}: {task['id']} — {task['domain']}")
        print(f"{'='*60}")

        task_result: dict = {
            "id": task["id"],
            "domain": task["domain"],
            "prompt": task["prompt"],
            "silver_standard": "",
            "gold_standard": None,
            "runs": [],
        }

        # Step 1: Silver standard — Gemini 2.5 Flash (always available)
        print("  [SILVER] Calling Gemini 2.5 Flash...")
        silver = call_gemini(task["prompt"])
        task_result["silver_standard"] = silver[:2000]
        print(f"  [SILVER] {len(silver)} chars")
        time.sleep(4)  # Gemini free tier: ~15 RPM

        # Step 2: Gold standard — Sonnet 4.6 (only in Claude Code session)
        print("  [GOLD] Calling Sonnet 4.6...")
        gold = call_sonnet(task["prompt"])
        if gold:
            task_result["gold_standard"] = gold[:2000]
            print(f"  [GOLD] {len(gold)} chars")
        else:
            task_result["gold_standard"] = None
            print("  [GOLD] Not available (no active Claude Code session)")

        # Use best available standard for evaluation
        reference = gold if gold else silver

        # Step 2: 5 runs per mode
        for run_idx in range(5):
            print(f"\n  --- Run {run_idx + 1}/5 ---")
            run_result: dict = {"run": run_idx + 1, "models": {}}

            # DQ OFF
            print("  [groq] DQ OFF...", end=" ", flush=True)
            resp_off = call_model(task["prompt"], use_dq=False)
            score_off = evaluate(reference, resp_off, task, "groq_dq_off")
            print(f"Score: {score_off.get('total', '?')}/50")

            # DQ ON
            print("  [groq] DQ ON...", end=" ", flush=True)
            resp_on = call_model(task["prompt"], use_dq=True)
            score_on = evaluate(reference, resp_on, task, "groq_dq_on")
            print(f"Score: {score_on.get('total', '?')}/50")

            update_enricher_feedback(task, score_on)

            run_result["models"]["groq"] = {
                "dq_off": {
                    "response_length": len(resp_off),
                    "score": score_off,
                    "hallucination": score_off.get("hallucination_detected", "unknown"),
                },
                "dq_on": {
                    "response_length": len(resp_on),
                    "score": score_on,
                    "hallucination": score_on.get("hallucination_detected", "unknown"),
                    "enricher_impact": score_on.get("enricher_impact", "unknown"),
                },
            }

            time.sleep(2)
            task_result["runs"].append(run_result)

        task_result["sonnet_available"] = gold is not None
        results["tasks"].append(task_result)

        # Save intermediate results
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  [SAVED] {report_path}")

    sonnet_count = sum(1 for t in results["tasks"] if t.get("sonnet_available"))
    results["metadata"]["sonnet_available_tasks"] = sonnet_count

    print_summary(results)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    generate_and_send_report(results, report_path)

    print(f"\n{'='*60}")
    print(f"BENCHMARK COMPLETE — {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_benchmark()
