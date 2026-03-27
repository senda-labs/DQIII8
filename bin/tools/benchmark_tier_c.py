#!/usr/bin/env python3
"""Mini-benchmark: qwen 7b with vs without DQ enrichment.

Tests the core DQ value proposition: making cheap local models (Tier C)
produce professional-quality answers by injecting domain knowledge they lack.

Usage:
    python3 bin/tools/benchmark_tier_c.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
import sys
import time
import urllib.request
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
OLLAMA_URL = "http://localhost:11434/api/generate"

sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

# 5 vague user queries that cross domains (DQ's sweet spot)
QUERIES = [
    {
        "prompt": "Quiero diseñar una app de nutrición personalizada",
        "domain": "natural_sciences",
        "keywords": ["BMR", "kcal", "macro", "protein", "body fat", "TDEE", "diet"],
    },
    {
        "prompt": "Cómo puedo construir un dashboard financiero con métricas de valoración",
        "domain": "social_sciences",
        "keywords": ["WACC", "DCF", "CAPM", "equity", "beta", "ratio", "valuation"],
    },
    {
        "prompt": "Quiero hacer un sistema de video con narración automática",
        "domain": "applied_sciences",
        "keywords": [
            "TTS",
            "ffmpeg",
            "subtitle",
            "audio",
            "pipeline",
            "render",
            "voice",
        ],
    },
    {
        "prompt": "Ayúdame a implementar un patrón async para llamadas API concurrentes",
        "domain": "applied_sciences",
        "keywords": [
            "async",
            "await",
            "gather",
            "semaphore",
            "coroutine",
            "event loop",
            "aiohttp",
        ],
    },
    {
        "prompt": "Necesito analizar si mi startup es viable financieramente",
        "domain": "social_sciences",
        "keywords": [
            "runway",
            "burn rate",
            "unit economics",
            "LTV",
            "CAC",
            "margin",
            "cash flow",
        ],
    },
]


def ollama_generate(prompt: str, model: str = "qwen2.5-coder:7b") -> str:
    data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read()).get("response", "")
    except Exception as e:
        return f"ERROR: {e}"


def get_dq_context(query: str, domain: str, top_k: int = 3) -> str:
    """Get relevant chunks from knowledge base."""
    try:
        import sqlite_vec
        from embeddings import get_embedding

        conn = sqlite3.connect(str(DB_PATH))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)

        emb = get_embedding(query)
        if not emb:
            conn.close()
            return ""

        emb_bytes = struct.pack(f"{len(emb)}f", *emb)
        rows = conn.execute(
            """SELECT vc.text, v.distance FROM vec_knowledge v
               JOIN vector_chunks vc ON vc.id = v.chunk_id
               WHERE v.embedding MATCH ? AND k = ?
               ORDER BY v.distance LIMIT ?""",
            (emb_bytes, top_k * 2, top_k * 2),
        ).fetchall()
        conn.close()

        # Filter by domain preference and score
        chunks = []
        for text, dist in rows:
            score = 1.0 - dist
            if score >= 0.55 and len(chunks) < top_k:
                chunks.append(text[:500])

        return "\n\n---\n\n".join(chunks)
    except Exception as exc:
        return f"[Context error: {exc}]"


def score_response(response: str, keywords: list[str]) -> dict:
    """Score response quality on multiple dimensions."""
    if not response or response.startswith("ERROR"):
        return {"keyword_hits": 0, "length": 0, "specificity": 0, "total": 0}

    text_lower = response.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    length = len(response)

    # Specificity: presence of numbers, formulas, concrete values
    import re

    has_numbers = len(re.findall(r"\d+\.?\d*", response)) > 2
    has_code = "```" in response or "def " in response
    has_formula = any(c in response for c in ["=", "→", "×", "÷"])
    specificity = sum([has_numbers, has_code, has_formula])

    keyword_score = (hits / max(len(keywords), 1)) * 4.0  # 0-4
    length_score = min(length / 400, 3.0)  # 0-3
    spec_score = specificity  # 0-3

    return {
        "keyword_hits": hits,
        "length": length,
        "specificity": specificity,
        "total": round(min(keyword_score + length_score + spec_score, 10.0), 2),
    }


def main() -> None:
    print(f"\n{'=' * 70}")
    print("  BENCHMARK TIER C: qwen2.5-coder:7b — CON vs SIN contexto DQ")
    print(f"  {len(QUERIES)} queries × 2 modes")
    print(f"{'=' * 70}")

    results: list[dict] = []

    for i, q in enumerate(QUERIES):
        print(f"\n{'─' * 70}")
        print(f"  QUERY {i + 1}/{len(QUERIES)}: {q['prompt']}")
        print(f"{'─' * 70}")

        # SIN DQ
        resp_off = ollama_generate(q["prompt"])
        score_off = score_response(resp_off, q["keywords"])

        # CON DQ
        ctx = get_dq_context(q["prompt"], q["domain"])
        prompt_on = (
            "Usa el siguiente contexto técnico para dar una respuesta "
            "profesional y estructurada:\n\n"
            f"CONTEXTO:\n{ctx}\n\n"
            f"PREGUNTA DEL USUARIO:\n{q['prompt']}\n\n"
            "RESPUESTA (profesional, estructurada, con datos concretos):"
        )
        resp_on = ollama_generate(prompt_on)
        score_on = score_response(resp_on, q["keywords"])

        delta = score_on["total"] - score_off["total"]
        marker = "+" if delta >= 0 else "!!"

        print(
            f"\n  SIN DQ: score={score_off['total']:5.2f}  keywords={score_off['keyword_hits']}/{len(q['keywords'])}  len={score_off['length']}"
        )
        print(
            f"  CON DQ: score={score_on['total']:5.2f}  keywords={score_on['keyword_hits']}/{len(q['keywords'])}  len={score_on['length']}"
        )
        print(f"  DELTA:  {delta:+.2f} {marker}")

        print(f"\n  --- SIN DQ (first 300 chars) ---")
        print(f"  {resp_off[:300]}")
        print(f"\n  --- CON DQ (first 300 chars) ---")
        print(f"  {resp_on[:300]}")

        results.append(
            {
                "query": q["prompt"],
                "domain": q["domain"],
                "off": score_off,
                "on": score_on,
                "delta": delta,
                "ctx_len": len(ctx),
            }
        )
        time.sleep(2)

    # Summary
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  {'Query':50s} {'OFF':>5s} {'ON':>5s} {'Delta':>7s}")
    print(f"  {'-' * 67}")

    total_off = total_on = 0
    for r in results:
        total_off += r["off"]["total"]
        total_on += r["on"]["total"]
        d = r["delta"]
        m = "+" if d >= 0 else "!!"
        print(
            f"  {r['query'][:50]:50s} {r['off']['total']:5.2f} {r['on']['total']:5.2f} {d:+7.2f} {m}"
        )

    avg_off = total_off / max(len(results), 1)
    avg_on = total_on / max(len(results), 1)
    avg_delta = avg_on - avg_off
    print(f"  {'-' * 67}")
    print(f"  {'AVERAGE':50s} {avg_off:5.2f} {avg_on:5.2f} {avg_delta:+7.2f}")
    print()


if __name__ == "__main__":
    main()
