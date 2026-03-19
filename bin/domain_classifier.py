#!/usr/bin/env python3
"""
JARVIS — Domain Classifier

Clasifica prompts en 5 dominios del conocimiento:
  formal_sciences · natural_sciences · social_sciences
  humanities_arts · applied_sciences

Pipeline:
  1. Keyword match ($0, <1ms) — rápido, sin red
  2. Embedding similarity via nomic-embed-text ($0, ~50-100ms) — si Ollama disponible

Uso:
    python3 bin/domain_classifier.py "tu prompt"
    python3 bin/domain_classifier.py --setup       # crea tabla + centroides
    python3 bin/domain_classifier.py --setup --force  # recalcula centroides
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

DB_PATH = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis")) / "database" / "jarvis_metrics.db"
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

DOMAINS: dict[str, dict] = {
    "formal_sciences": {
        "keywords": [
            "mathematics",
            "math",
            "matemáticas",
            "algebra",
            "calculus",
            "logic",
            "lógica",
            "statistics",
            "estadística",
            "probability",
            "algorithm",
            "computation",
            "computación",
            "theorem",
            "proof",
            "set theory",
            "geometry",
            "geometría",
        ],
        "description": "Mathematics, logic, statistics, computation, algorithms",
    },
    "natural_sciences": {
        "keywords": [
            "physics",
            "física",
            "chemistry",
            "química",
            "biology",
            "biología",
            "ecology",
            "ecología",
            "geology",
            "geología",
            "astronomy",
            "astronomía",
            "quantum",
            "molecular",
            "genetics",
            "evolution",
            "evolución",
            "thermodynamics",
            "electromagnetism",
        ],
        "description": "Physics, chemistry, biology, ecology, geology, astronomy",
    },
    "social_sciences": {
        "keywords": [
            "economics",
            "economía",
            "economy",
            "psychology",
            "psicología",
            "sociology",
            "sociología",
            "politics",
            "política",
            "anthropology",
            "antropología",
            "demographics",
            "demographic",
            "behavior",
            "comportamiento",
            "market",
            "mercado",
            "policy",
            "governance",
        ],
        "description": "Economics, psychology, sociology, politics, anthropology",
    },
    "humanities_arts": {
        "keywords": [
            "literature",
            "literatura",
            "philosophy",
            "filosofía",
            "history",
            "historia",
            "art",
            "arte",
            "music",
            "música",
            "language",
            "idioma",
            "linguistics",
            "lingüística",
            "culture",
            "cultura",
            "poetry",
            "poesía",
            "narrative",
            "narrativa",
            "rhetoric",
            "ethics",
            "ética",
        ],
        "description": "Literature, philosophy, history, art, music, linguistics",
    },
    "applied_sciences": {
        "keywords": [
            "engineering",
            "ingeniería",
            "medicine",
            "medicina",
            "technology",
            "tecnología",
            "architecture",
            "arquitectura",
            "agriculture",
            "agricultura",
            "robotics",
            "robotics",
            "networks",
            "redes",
            "software",
            "hardware",
            "infrastructure",
            "clinical",
            "clínico",
            "manufacturing",
        ],
        "description": "Engineering, medicine, technology, architecture, agriculture",
    },
}


# ── Embedding helpers ────────────────────────────────────────────────────────


def _get_embedding(text: str) -> list[float] | None:
    """Llama a nomic-embed-text via Ollama. Devuelve None si no está disponible."""
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosemgrep
            data = json.loads(resp.read())
            return data.get("embedding")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _pack_embedding(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x**2 for x in a) ** 0.5
    norm_b = sum(x**2 for x in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-9)


# ── DB setup ─────────────────────────────────────────────────────────────────


def setup_db(force: bool = False) -> None:
    """Crea la tabla domain_enrichment y calcula centroides vía Ollama."""
    if not DB_PATH.exists():
        print(f"[domain_classifier] DB no encontrada: {DB_PATH}", file=sys.stderr)
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_enrichment (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT    NOT NULL,
            keywords    TEXT    NOT NULL,  -- JSON array
            centroid    BLOB,              -- packed float32 embedding
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_name ON domain_enrichment (name)")
    conn.commit()

    for domain_name, info in DOMAINS.items():
        existing = conn.execute(
            "SELECT id, centroid FROM domain_enrichment WHERE name = ?",
            (domain_name,),
        ).fetchone()

        if existing and not force and existing[1] is not None:
            print(f"  ✓ {domain_name} — ya tiene centroide (usa --force para recalcular)")
            continue

        # Calcular centroide: embedding del texto descriptivo + keywords
        centroid_text = info["description"] + ". Keywords: " + ", ".join(info["keywords"])
        print(f"  → Calculando centroide para {domain_name}...", end="", flush=True)
        vec = _get_embedding(centroid_text)

        centroid_blob = _pack_embedding(vec) if vec else None
        status = "✓" if vec else "✗ (Ollama no disponible — centroide null)"

        if existing:
            conn.execute(
                "UPDATE domain_enrichment SET description=?, keywords=?, centroid=?, updated_at=datetime('now') WHERE name=?",
                (info["description"], json.dumps(info["keywords"]), centroid_blob, domain_name),
            )
        else:
            conn.execute(
                "INSERT INTO domain_enrichment (name, description, keywords, centroid) VALUES (?,?,?,?)",
                (domain_name, info["description"], json.dumps(info["keywords"]), centroid_blob),
            )
        conn.commit()
        print(f" {status}")

    conn.close()
    print("[domain_classifier] Setup completo.")


# ── Classification ────────────────────────────────────────────────────────────


def _classify_by_keywords(prompt_lower: str) -> str | None:
    """Matching por keywords. Devuelve el dominio con más hits, o None."""
    scores: dict[str, int] = {}
    for domain_name, info in DOMAINS.items():
        hits = sum(1 for kw in info["keywords"] if kw in prompt_lower)
        if hits:
            scores[domain_name] = hits
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def _classify_by_embedding(prompt: str) -> tuple[str, float] | None:
    """
    Embedding similarity contra centroides almacenados en DB.
    Devuelve (domain_name, score) o None si Ollama / DB no disponibles.
    """
    if not DB_PATH.exists():
        return None

    prompt_vec = _get_embedding(prompt)
    if prompt_vec is None:
        return None

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        rows = conn.execute(
            "SELECT name, centroid FROM domain_enrichment WHERE centroid IS NOT NULL"
        ).fetchall()
        conn.close()
    except Exception:
        return None

    if not rows:
        return None

    best_name, best_score = "", -1.0
    for name, blob in rows:
        if blob:
            centroid = _unpack_embedding(blob)
            score = _cosine(prompt_vec, centroid)
            if score > best_score:
                best_score, best_name = score, name

    return (best_name, round(best_score, 4)) if best_name else None


def classify_domain(prompt: str) -> tuple[str, float, str]:
    """
    Clasifica el dominio del prompt.

    Returns:
        (domain_name, confidence, method)
        method: 'keyword' | 'embedding' | 'default'
    """
    prompt_lower = prompt.lower()

    # 1. Keyword match (fast)
    kw_domain = _classify_by_keywords(prompt_lower)
    if kw_domain:
        return kw_domain, 1.0, "keyword"

    # 2. Embedding similarity (slower)
    emb_result = _classify_by_embedding(prompt)
    if emb_result:
        domain, score = emb_result
        return domain, score, "embedding"

    # 3. Default
    return "applied_sciences", 0.0, "default"


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    args = sys.argv[1:]

    if "--setup" in args:
        force = "--force" in args
        print("─── Domain Enrichment Setup ───")
        setup_db(force=force)
        return

    if not args:
        print('Uso: python3 bin/domain_classifier.py "prompt"', file=sys.stderr)
        print("     python3 bin/domain_classifier.py --setup [--force]", file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(a for a in args if not a.startswith("--"))
    domain, score, method = classify_domain(prompt)
    print(f"domain={domain} score={score:.4f} method={method}")


if __name__ == "__main__":
    main()
