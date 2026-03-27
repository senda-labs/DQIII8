#!/usr/bin/env python3
"""DQ Knowledge Harvester v2 — Automated knowledge acquisition with 5 quality gates.

Downloads papers from academic sources, evaluates significance, extracts text
(discarding PDFs immediately), creates semantic chunks with contextual prefixes,
classifies into DQ's 5 domains, and inserts into the knowledge base.

DOES NOT store PDFs — only extracted, curated chunks survive.

Usage:
    python3 bin/tools/knowledge_harvester.py --harvest --max 10
    python3 bin/tools/knowledge_harvester.py --harvest --domain formal_sciences --max 5
    python3 bin/tools/knowledge_harvester.py --harvest --query "retrieval augmented generation" --max 3
    python3 bin/tools/knowledge_harvester.py --ingest /path/to/file.pdf --domain applied_sciences
    python3 bin/tools/knowledge_harvester.py --ingest /path/to/file.md --project auto-report
    python3 bin/tools/knowledge_harvester.py --status
    python3 bin/tools/knowledge_harvester.py --cleanup
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import struct
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"

sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))

log = logging.getLogger("harvester")

# ── Configuration ────────────────────────────────────────────────────────────

SOURCES: dict[str, dict] = {
    "arxiv": {
        "enabled": True,
        "domains": {
            "formal_sciences": ["cs.AI", "cs.LG", "stat.ML", "math.OC"],
            "natural_sciences": ["q-bio", "physics.bio-ph", "cond-mat"],
            "social_sciences": ["econ.GN", "q-fin", "cs.CY", "cs.GT"],
            "applied_sciences": ["cs.SE", "cs.DB", "cs.CR", "cs.IR"],
            "humanities_arts": ["cs.CL", "cs.SD", "cs.MM"],
        },
        "rate_limit_s": 3,
        "max_per_domain": 5,
        "recency_days": 14,
    },
    "openalex": {
        "enabled": True,
        "domains": {
            "social_sciences": ["economics", "political science"],
            "humanities_arts": ["philosophy", "linguistics"],
            "natural_sciences": ["biology", "chemistry"],
            "formal_sciences": ["mathematics", "computer science"],
            "applied_sciences": ["engineering"],
        },
        "rate_limit_s": 1,
        "max_per_domain": 5,
        "recency_days": 30,
    },
    "semantic_scholar": {
        "enabled": True,
        "domains": "all",
        "rate_limit_s": 5,
        "max_per_domain": 3,
        "recency_days": 14,
    },
}

SIGNIFICANCE_THRESHOLD = 0.5
MAX_CHUNKS_PER_PAPER = 15
CHUNK_MIN_CHARS = 200
CHUNK_MAX_CHARS = 800
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

# ── Harvest Log Table ────────────────────────────────────────────────────────

CREATE_HARVEST_LOG = """\
CREATE TABLE IF NOT EXISTS harvest_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL UNIQUE,
    title           TEXT,
    domain          TEXT,
    significance    REAL,
    gate_passed     TEXT,
    chunks_created  INTEGER DEFAULT 0,
    harvested_at    TEXT DEFAULT (datetime('now'))
)"""


def _init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(CREATE_HARVEST_LOG)
    conn.commit()
    return conn


def _is_already_harvested(conn: sqlite3.Connection, source_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM harvest_log WHERE source_id = ?", (source_id,)
    ).fetchone()
    return row is not None


def _log_harvest(
    conn: sqlite3.Connection,
    source: str,
    source_id: str,
    title: str,
    domain: str,
    significance: float,
    gate: str,
    chunks: int = 0,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO harvest_log "
        "(source, source_id, title, domain, significance, gate_passed, chunks_created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source, source_id, title, domain, significance, gate, chunks),
    )
    conn.commit()


# ── Embeddings (reuse Ollama nomic-embed-text) ──────────────────────────────


def _get_embedding(text: str) -> list[float] | None:
    """Get embedding via Ollama nomic-embed-text (768 dims)."""
    try:
        payload = json.dumps({"model": EMBED_MODEL, "prompt": text[:8000]}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            OLLAMA_EMBED_URL,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))["embedding"]
    except Exception as exc:
        log.warning("Embedding failed: %s", exc)
        return None


def _serialize_embedding(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


# ── Chunk hash (same as enricher _chunk_hash) ───────────────────────────────


def _chunk_hash(text: str) -> str:
    return hashlib.sha256(text[:200].encode("utf-8")).hexdigest()


# ── Source Fetchers ──────────────────────────────────────────────────────────

FetchResult = dict[
    str, Any
]  # title, abstract, url, pdf_url, authors, date, source, source_id, citations, venue


def _fetch_arxiv(
    domain: str, categories: list[str], max_results: int, recency_days: int
) -> list[FetchResult]:
    """Fetch papers from arXiv API."""
    try:
        import arxiv
    except ImportError:
        log.warning("arxiv not installed — skipping arXiv source")
        return []

    results: list[FetchResult] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)

    for cat in categories:
        try:
            search = arxiv.Search(
                query=f"cat:{cat}",
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            client = arxiv.Client()
            for paper in client.results(search):
                pub_date = paper.published
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                if pub_date < cutoff:
                    continue
                results.append(
                    {
                        "title": paper.title,
                        "abstract": paper.summary or "",
                        "url": paper.entry_id,
                        "pdf_url": paper.pdf_url,
                        "authors": [a.name for a in paper.authors[:5]],
                        "date": pub_date.strftime("%Y-%m-%d"),
                        "source": "arxiv",
                        "source_id": f"arxiv:{paper.entry_id.split('/')[-1]}",
                        "citations": 0,
                        "venue": cat,
                    }
                )
            time.sleep(SOURCES["arxiv"]["rate_limit_s"])
        except Exception as exc:
            log.warning("arXiv fetch failed for %s: %s", cat, exc)

    return results[:max_results]


def _fetch_openalex(
    domain: str, concepts: list[str], max_results: int, recency_days: int
) -> list[FetchResult]:
    """Fetch papers from OpenAlex API."""
    results: list[FetchResult] = []
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=recency_days)).strftime(
        "%Y-%m-%d"
    )

    for concept in concepts:
        try:
            url = (
                f"https://api.openalex.org/works?"
                f"filter=from_publication_date:{cutoff_date},"
                f"default.search:{urllib.request.quote(concept)}"
                f"&sort=publication_date:desc&per_page={max_results}"
                f"&mailto=guilleikersymv@gmail.com"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "DQIII8/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for work in data.get("results", []):
                abstract = ""
                inverted = work.get("abstract_inverted_index")
                if inverted:
                    words: dict[int, str] = {}
                    for word, positions in inverted.items():
                        for pos in positions:
                            words[pos] = word
                    abstract = " ".join(words[k] for k in sorted(words))

                pdf_url = None
                oa = work.get("open_access", {})
                if oa.get("oa_url"):
                    pdf_url = oa["oa_url"]

                results.append(
                    {
                        "title": work.get("title", ""),
                        "abstract": abstract,
                        "url": work.get("id", ""),
                        "pdf_url": pdf_url,
                        "authors": [
                            a.get("author", {}).get("display_name", "")
                            for a in (work.get("authorships") or [])[:5]
                        ],
                        "date": work.get("publication_date", ""),
                        "source": "openalex",
                        "source_id": f"openalex:{work.get('id', '').split('/')[-1]}",
                        "citations": work.get("cited_by_count", 0),
                        "venue": (
                            (work.get("primary_location", {}) or {})
                            .get("source", {})
                            .get("display_name", concept)
                            if work.get("primary_location")
                            else concept
                        ),
                    }
                )
            time.sleep(SOURCES["openalex"]["rate_limit_s"])
        except Exception as exc:
            log.warning("OpenAlex fetch failed for %s: %s", concept, exc)

    return results[:max_results]


def _fetch_semantic_scholar(query: str, max_results: int) -> list[FetchResult]:
    """Fetch papers from Semantic Scholar API."""
    results: list[FetchResult] = []
    try:
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search?"
            f"query={urllib.request.quote(query)}"
            f"&fields=title,abstract,url,year,authors,citationCount,venue"
            f"&limit={max_results}"
        )
        headers: dict[str, str] = {"User-Agent": "DQIII8/1.0"}
        s2_key = os.environ.get("S2_API_KEY", "")
        if s2_key:
            headers["x-api-key"] = s2_key
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for paper in data.get("data", []):
            results.append(
                {
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract", "") or "",
                    "url": paper.get("url", ""),
                    "pdf_url": None,
                    "authors": [
                        a.get("name", "") for a in (paper.get("authors") or [])[:5]
                    ],
                    "date": f"{paper.get('year', 2026)}-01-01",
                    "source": "semantic_scholar",
                    "source_id": f"s2:{paper.get('paperId', '')}",
                    "citations": paper.get("citationCount", 0) or 0,
                    "venue": paper.get("venue", "") or "",
                }
            )
    except Exception as exc:
        log.warning("Semantic Scholar fetch failed: %s", exc)

    return results[:max_results]


# ── Gate 1: Significance Scoring ─────────────────────────────────────────────


def _recency_score(date_str: str) -> float:
    try:
        pub = datetime.strptime(date_str[:10], "%Y-%m-%d")
        age = (datetime.now() - pub).days
    except Exception:
        return 0.1
    if age <= 7:
        return 0.3
    if age <= 30:
        return 0.2
    if age <= 90:
        return 0.1
    return 0.05


def _novelty_score(abstract: str) -> float:
    """How different is this from existing knowledge base? Uses embedding similarity."""
    if not abstract or len(abstract) < 50:
        return 0.2

    try:
        from vector_store import search_vectors as _vs_search
        from vector_store import _embed_query as _vs_embed

        emb = _vs_embed(abstract[:500])
        if emb is None:
            return 0.2
        hits = _vs_search(emb, top_k=3)
        if not hits:
            return 0.4  # Empty KB — everything is novel

        max_sim = max(1.0 - float(r.get("distance", 1.0)) for r in hits)
        # sim > 0.85 → duplicate → novelty 0
        # sim < 0.4 → very novel → novelty 0.4
        return round(max(0, 0.4 * (1 - max_sim / 0.85)), 3)
    except Exception:
        return 0.2


def _impact_score(item: FetchResult) -> float:
    citations = item.get("citations", 0) or 0
    venue = (item.get("venue", "") or "").lower()
    top_venues = [
        "nature",
        "science",
        "neurips",
        "icml",
        "iclr",
        "acl",
        "emnlp",
        "sigir",
        "cvpr",
        "aaai",
        "lancet",
        "cell",
        "pnas",
    ]
    venue_bonus = 0.1 if any(v in venue for v in top_venues) else 0
    if citations > 50:
        return 0.3
    if citations > 10:
        return 0.2 + venue_bonus
    return 0.1 + venue_bonus


def significance_score(item: FetchResult) -> float:
    recency = _recency_score(item.get("date", ""))
    novelty = _novelty_score(item.get("abstract", ""))
    impact = _impact_score(item)
    return round(recency + novelty + impact, 3)


# ── Gate 2: Text Extraction ──────────────────────────────────────────────────


def _clean_paper_text(text: str) -> str:
    """Remove references section, headers/footers, page numbers."""
    # Remove everything after References section
    for marker in ["References\n", "REFERENCES\n", "Bibliography\n"]:
        idx = text.find(marker)
        if idx > len(text) * 0.5:
            text = text[:idx]
            break

    # Remove page numbers (standalone digits on a line)
    text = re.sub(r"^\d{1,3}\s*$", "", text, flags=re.MULTILINE)
    # Remove excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(item: FetchResult) -> str | None:
    """Extract text from paper. DOES NOT store PDFs on disk."""
    # Try PDF first
    if item.get("pdf_url"):
        try:
            import fitz

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                urllib.request.urlretrieve(item["pdf_url"], tmp.name)
                doc = fitz.open(tmp.name)
                text = "\n".join(page.get_text() for page in doc)
                doc.close()
            cleaned = _clean_paper_text(text)
            if len(cleaned) > 200:
                return cleaned
        except Exception as exc:
            log.warning(
                "PDF extraction failed for %s: %s", item.get("source_id", "?"), exc
            )

    # Try web article (trafilatura)
    if item.get("url") and item.get("source") in ("hackernews", "openalex"):
        try:
            import trafilatura

            downloaded = trafilatura.fetch_url(item["url"])
            if downloaded:
                extracted = trafilatura.extract(downloaded)
                if extracted and len(extracted) > 200:
                    return extracted
        except Exception:
            pass

    # Fallback: abstract only
    abstract = item.get("abstract", "")
    return abstract if len(abstract) > 100 else None


def extract_local_file(filepath: Path) -> str | None:
    """Extract text from local file. Supports PDF, TXT, MD."""
    suffix = filepath.suffix.lower()

    if suffix == ".pdf":
        try:
            import fitz

            doc = fitz.open(str(filepath))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return _clean_paper_text(text) if len(text) > 100 else None
        except Exception as exc:
            log.error("PDF extraction failed for %s: %s", filepath, exc)
            return None

    if suffix in (".txt", ".md", ".rst"):
        return filepath.read_text(encoding="utf-8")

    log.warning("Unsupported file type: %s", suffix)
    return None


# ── Gate 3: Semantic Chunking + Contextual Prefix ────────────────────────────


def _detect_sections(text: str) -> list[tuple[str, str]]:
    """Split text into (section_name, section_text) pairs."""
    header_pattern = re.compile(
        r"^(#{1,3}\s+.+|(?:Abstract|Introduction|Methods?|Results?|Discussion|"
        r"Conclusion|Background|Related Work|Experiments?|Analysis|Methodology)\s*$)",
        re.MULTILINE | re.IGNORECASE,
    )
    matches = list(header_pattern.finditer(text))

    if not matches:
        return [("Content", text)]

    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        name = m.group(0).strip().lstrip("#").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((name, body))

    # Add any text before the first header
    preamble = text[: matches[0].start()].strip()
    if len(preamble) > 100:
        sections.insert(0, ("Preamble", preamble))

    return sections


def _split_into_chunks(text: str) -> list[str]:
    """Split text into chunks respecting CHUNK_MIN/MAX_CHARS."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= CHUNK_MAX_CHARS:
            current = f"{current}\n\n{para}" if current else para
        else:
            if len(current) >= CHUNK_MIN_CHARS:
                chunks.append(current.strip())
            elif current:
                # Too short — merge with next
                current = f"{current}\n\n{para}"
                continue
            current = para

    if current and len(current) >= CHUNK_MIN_CHARS:
        chunks.append(current.strip())
    elif current and chunks:
        # Merge remainder with last chunk
        chunks[-1] = f"{chunks[-1]}\n\n{current}"

    # Split any chunks that are still too long
    final: list[str] = []
    for c in chunks:
        if len(c) <= CHUNK_MAX_CHARS:
            final.append(c)
        else:
            # Hard split at sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", c)
            part = ""
            for s in sentences:
                if len(part) + len(s) + 1 <= CHUNK_MAX_CHARS:
                    part = f"{part} {s}" if part else s
                else:
                    if len(part) >= CHUNK_MIN_CHARS:
                        final.append(part.strip())
                    part = s
            if part and len(part) >= CHUNK_MIN_CHARS:
                final.append(part.strip())

    return final


def create_chunks(
    text: str,
    item: FetchResult | None = None,
    source_tag: str = "",
    year: str = "",
) -> list[dict]:
    """Create semantic chunks with contextual prefix.

    Returns list of {text, source, section, chunk_idx}.
    """
    title = (item or {}).get("title", "")
    src = source_tag or (item or {}).get("source", "unknown")
    yr = year or (item or {}).get("date", "")[:4]

    sections = _detect_sections(text)
    all_chunks: list[dict] = []

    for section_name, section_text in sections:
        raw_chunks = _split_into_chunks(section_text)
        for chunk_text in raw_chunks:
            # Contextual prefix
            prefix_parts = [src.upper()]
            if title:
                prefix_parts.append(f'"{title[:60]}"')
            if yr:
                prefix_parts.append(f"({yr})")
            prefix_parts.append(section_name)
            prefix = f"[{': '.join(prefix_parts[:2])}, {', '.join(prefix_parts[2:])}]"

            full_text = f"{prefix} {chunk_text}"
            all_chunks.append(
                {
                    "text": full_text,
                    "source": f"{src}:{title[:80]}" if title else src,
                    "section": section_name,
                    "chunk_idx": len(all_chunks),
                }
            )

    # Limit to MAX_CHUNKS_PER_PAPER — keep chunks with most content
    if len(all_chunks) > MAX_CHUNKS_PER_PAPER:
        all_chunks.sort(key=lambda c: len(c["text"]), reverse=True)
        all_chunks = all_chunks[:MAX_CHUNKS_PER_PAPER]
        all_chunks.sort(key=lambda c: c["chunk_idx"])

    return all_chunks


# ── Gate 4: Classification + Centroid Validation ─────────────────────────────


def classify_chunk(text: str) -> tuple[str, float]:
    """Classify chunk into one of 5 domains. Returns (domain, confidence)."""
    try:
        from domain_classifier import classify_domain

        domain, confidence, _method = classify_domain(text[:500])
        return domain, confidence
    except Exception:
        return _keyword_classify_fallback(text), 0.5


def _keyword_classify_fallback(text: str) -> str:
    """Simple keyword fallback when domain_classifier is unavailable."""
    t = text.lower()
    scores: dict[str, int] = {
        "formal_sciences": 0,
        "natural_sciences": 0,
        "social_sciences": 0,
        "applied_sciences": 0,
        "humanities_arts": 0,
    }
    kw_map = {
        "formal_sciences": [
            "algorithm",
            "theorem",
            "proof",
            "optimization",
            "bayesian",
            "statistics",
            "mathematical",
        ],
        "natural_sciences": [
            "protein",
            "gene",
            "cell",
            "molecule",
            "species",
            "neuron",
            "chemical",
            "physics",
        ],
        "social_sciences": [
            "market",
            "economic",
            "policy",
            "finance",
            "gdp",
            "inflation",
            "investment",
        ],
        "applied_sciences": [
            "software",
            "api",
            "database",
            "python",
            "code",
            "system",
            "engineering",
        ],
        "humanities_arts": [
            "narrative",
            "language",
            "culture",
            "philosophy",
            "art",
            "literature",
            "linguistic",
        ],
    }
    for domain, keywords in kw_map.items():
        for kw in keywords:
            if kw in t:
                scores[domain] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "applied_sciences"


# ── Gate 5: Insertion ────────────────────────────────────────────────────────


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension."""
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as exc:
        log.warning("sqlite-vec not available: %s", exc)


def insert_chunks(
    conn: sqlite3.Connection,
    chunks: list[dict],
    domain: str,
    agent_name: str = "",
) -> int:
    """Insert chunks into vector_chunks + chunks_fts + vec_knowledge.

    Returns number of chunks successfully inserted.
    """
    _load_sqlite_vec(conn)
    inserted = 0

    for chunk in chunks:
        text = chunk["text"]
        source = chunk["source"]
        chunk_idx = chunk["chunk_idx"]

        # Dedup check via SHA256(text[:200])
        ch = _chunk_hash(text)
        existing = conn.execute(
            "SELECT 1 FROM vector_chunks WHERE source = ? AND chunk_id = ? AND domain = ?",
            (source, chunk_idx, domain),
        ).fetchone()
        if existing:
            continue

        # Also check by content hash for cross-source dedup
        all_texts = conn.execute(
            "SELECT text FROM vector_chunks WHERE domain = ? LIMIT 2000", (domain,)
        ).fetchall()
        if any(_chunk_hash(r[0]) == ch for r in all_texts):
            continue

        # Generate embedding
        embedding = _get_embedding(text)
        if not embedding:
            log.warning("Embedding failed for chunk %d of %s", chunk_idx, source)
            continue

        try:
            # Insert into vector_chunks
            cur = conn.execute(
                "INSERT INTO vector_chunks (source, chunk_id, agent_name, domain, text) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, chunk_idx, agent_name, domain, text),
            )
            row_id = cur.lastrowid

            # Sync FTS5
            conn.execute(
                "INSERT INTO chunks_fts(rowid, source, text, domain, agent_name) "
                "VALUES (?, ?, ?, ?, ?)",
                (row_id, source, text, domain or "", agent_name),
            )

            # Insert embedding into vec_knowledge
            blob = _serialize_embedding(embedding)
            conn.execute("DELETE FROM vec_knowledge WHERE chunk_id = ?", (row_id,))
            conn.execute(
                "INSERT INTO vec_knowledge (chunk_id, embedding) VALUES (?, ?)",
                (row_id, blob),
            )

            conn.commit()
            inserted += 1

        except sqlite3.IntegrityError:
            conn.rollback()
            continue
        except Exception as exc:
            conn.rollback()
            log.warning("Insert failed for chunk %d: %s", chunk_idx, exc)
            continue

    return inserted


def _generate_key_facts_for_chunks(
    conn: sqlite3.Connection, source: str, domain: str
) -> None:
    """Generate key_facts for newly inserted chunks (best-effort)."""
    try:
        env_file = DQIII8_ROOT / "my-projects" / "auto-report" / ".env"
        if not env_file.exists():
            return
        groq_key = ""
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GROQ_API_KEY="):
                groq_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
        if not groq_key:
            return

        rows = conn.execute(
            "SELECT id, text FROM vector_chunks WHERE source = ? AND domain = ?",
            (source, domain),
        ).fetchall()

        for row_id, text in rows:
            ch = _chunk_hash(text)
            already = conn.execute(
                "SELECT 1 FROM chunk_key_facts WHERE chunk_hash = ?", (ch,)
            ).fetchone()
            if already:
                continue

            prompt = (
                f"Extract 3-5 key facts from this {domain.replace('_', ' ')} knowledge chunk. "
                "Return ONLY a JSON array of short strings (max 15 words each). "
                f"No explanation, no markdown fences.\n\nCHUNK:\n{text[:800]}"
            )
            payload = json.dumps(
                {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 256,
                    "temperature": 0.0,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw = data["choices"][0]["message"]["content"].strip()

                if raw.startswith("```"):
                    lines = raw.splitlines()
                    raw = "\n".join(
                        lines[1:-1] if lines[-1].startswith("```") else lines[1:]
                    )

                facts = json.loads(raw)
                if isinstance(facts, list) and all(isinstance(f, str) for f in facts):
                    conn.execute(
                        "INSERT OR IGNORE INTO chunk_key_facts "
                        "(chunk_hash, source, domain, key_facts, generated_by) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            ch,
                            source,
                            domain,
                            json.dumps(facts, ensure_ascii=False),
                            "llama-3.3-70b-versatile",
                        ),
                    )
                    conn.commit()
                time.sleep(1.5)
            except Exception:
                pass  # Best-effort, don't block insertion
    except Exception:
        pass


# ── Main Harvest Pipeline ────────────────────────────────────────────────────


def harvest(
    target_domain: str | None = None,
    query: str | None = None,
    max_papers: int = 10,
    dry_run: bool = False,
) -> dict[str, int]:
    """Run the full 5-gate harvest pipeline.

    Returns stats dict with counts per gate.
    """
    conn = _init_db()
    stats: dict[str, int] = {
        "discovered": 0,
        "significant": 0,
        "extracted": 0,
        "chunked": 0,
        "inserted": 0,
        "rejected_dup": 0,
        "rejected_sig": 0,
    }

    # ── Gate 0: Discovery ────────────────────────────────────────────────
    all_items: list[FetchResult] = []

    if query:
        # Direct query mode — use Semantic Scholar
        print(f"[G0] Searching: '{query}'")
        all_items = _fetch_semantic_scholar(query, max_papers)
    else:
        # Domain-based harvesting
        domains_to_process = (
            [target_domain]
            if target_domain
            else list(SOURCES["arxiv"]["domains"].keys())
        )

        for domain in domains_to_process:
            # arXiv
            arxiv_cfg = SOURCES["arxiv"]
            if arxiv_cfg["enabled"] and domain in arxiv_cfg["domains"]:
                cats = arxiv_cfg["domains"][domain]
                items = _fetch_arxiv(
                    domain, cats, arxiv_cfg["max_per_domain"], arxiv_cfg["recency_days"]
                )
                for item in items:
                    item["_target_domain"] = domain
                all_items.extend(items)

            # OpenAlex
            oa_cfg = SOURCES["openalex"]
            if oa_cfg["enabled"] and domain in oa_cfg.get("domains", {}):
                concepts = oa_cfg["domains"][domain]
                items = _fetch_openalex(
                    domain, concepts, oa_cfg["max_per_domain"], oa_cfg["recency_days"]
                )
                for item in items:
                    item["_target_domain"] = domain
                all_items.extend(items)

    stats["discovered"] = len(all_items)
    print(f"[G0] Discovered: {len(all_items)} papers")

    if dry_run:
        for item in all_items[:10]:
            sig = significance_score(item)
            mark = "+" if sig >= SIGNIFICANCE_THRESHOLD else "-"
            print(f"  {mark} [{sig:.2f}] {item['source']}: {item['title'][:60]}")
        print(
            f"\n[DRY RUN] Would process up to {min(len(all_items), max_papers)} papers"
        )
        conn.close()
        return stats

    # Process papers through gates
    papers_processed = 0

    for item in all_items:
        if papers_processed >= max_papers:
            break

        source_id = item["source_id"]

        # Dedup against harvest_log
        if _is_already_harvested(conn, source_id):
            stats["rejected_dup"] += 1
            continue

        # ── Gate 1: Significance ─────────────────────────────────────────
        sig = significance_score(item)
        if sig < SIGNIFICANCE_THRESHOLD:
            _log_harvest(
                conn,
                item["source"],
                source_id,
                item["title"],
                "",
                sig,
                "rejected_significance",
            )
            stats["rejected_sig"] += 1
            continue
        stats["significant"] += 1
        print(f"  [G1] [{sig:.2f}] {item['title'][:50]}...")

        # ── Gate 2: Extraction ───────────────────────────────────────────
        text = extract_text(item)
        if not text:
            _log_harvest(
                conn,
                item["source"],
                source_id,
                item["title"],
                "",
                sig,
                "rejected_extraction",
            )
            continue
        stats["extracted"] += 1
        print(f"  [G2] Extracted {len(text)} chars")

        # ── Gate 3: Chunking ─────────────────────────────────────────────
        source_tag = item["source"]
        chunks = create_chunks(text, item, source_tag)
        if not chunks:
            _log_harvest(
                conn,
                item["source"],
                source_id,
                item["title"],
                "",
                sig,
                "rejected_chunking",
            )
            continue
        stats["chunked"] += len(chunks)
        print(f"  [G3] {len(chunks)} chunks created")

        # ── Gate 4: Classification ───────────────────────────────────────
        target = item.get("_target_domain", "")
        if target:
            domain = target
        else:
            domain, _conf = classify_chunk(chunks[0]["text"])
        print(f"  [G4] Domain: {domain}")

        # ── Gate 5: Insertion ────────────────────────────────────────────
        n_inserted = insert_chunks(conn, chunks, domain)
        stats["inserted"] += n_inserted
        print(f"  [G5] Inserted {n_inserted}/{len(chunks)} chunks")

        _log_harvest(
            conn,
            item["source"],
            source_id,
            item["title"],
            domain,
            sig,
            "inserted",
            n_inserted,
        )

        # Best-effort key_facts generation
        if n_inserted > 0:
            source_key = chunks[0]["source"]
            _generate_key_facts_for_chunks(conn, source_key, domain)

        papers_processed += 1

    conn.close()
    return stats


# ── Ingest Local File ────────────────────────────────────────────────────────


def ingest_file(filepath: str, domain: str = "", project: str = "") -> dict[str, int]:
    """Ingest a local file. Skips Gate 0 (discovery) and Gate 1 (significance)."""
    fp = Path(filepath)
    if not fp.exists():
        log.error("File not found: %s", filepath)
        return {"errors": 1}

    conn = _init_db()
    stats: dict[str, int] = {"extracted": 0, "chunked": 0, "inserted": 0}

    # Source tag
    if project:
        source_tag = f"user:{project}"
    else:
        source_tag = "user"

    source_id = f"user:{fp.name}"
    if _is_already_harvested(conn, source_id):
        print(f"[SKIP] Already ingested: {fp.name}")
        conn.close()
        return stats

    # Gate 2: Extract
    text = extract_local_file(fp)
    if not text:
        print(f"[ERROR] Could not extract text from {fp.name}")
        conn.close()
        return stats
    stats["extracted"] = 1
    print(f"[G2] Extracted {len(text)} chars from {fp.name}")

    # Gate 3: Chunk
    chunks = create_chunks(text, source_tag=source_tag, year="")
    if not chunks:
        print(f"[ERROR] No chunks created from {fp.name}")
        conn.close()
        return stats
    stats["chunked"] = len(chunks)
    print(f"[G3] {len(chunks)} chunks created")

    # Gate 4: Classification
    if not domain:
        domain, _conf = classify_chunk(chunks[0]["text"])
    print(f"[G4] Domain: {domain}")

    # Gate 5: Insert
    n_inserted = insert_chunks(conn, chunks, domain)
    stats["inserted"] = n_inserted
    print(f"[G5] Inserted {n_inserted}/{len(chunks)} chunks")

    _log_harvest(conn, "user", source_id, fp.name, domain, 1.0, "inserted", n_inserted)

    if n_inserted > 0:
        source_key = chunks[0]["source"]
        _generate_key_facts_for_chunks(conn, source_key, domain)

    conn.close()
    return stats


# ── Status + Cleanup ─────────────────────────────────────────────────────────


def show_status() -> None:
    """Show harvest statistics."""
    conn = _init_db()

    total = conn.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE text IS NOT NULL AND text != ''"
    ).fetchone()[0]

    print(f"\n{'=' * 55}")
    print(f"  Knowledge Base Status — {total} total chunks")
    print(f"{'=' * 55}")

    # By source prefix
    print("\n  By source type:")
    for prefix in ("arxiv:", "openalex:", "s2:", "user:", "hackernews:"):
        cnt = conn.execute(
            "SELECT COUNT(*) FROM vector_chunks WHERE source LIKE ?",
            (f"{prefix}%",),
        ).fetchone()[0]
        if cnt > 0:
            print(f"    {prefix:20s} {cnt:4d} chunks")

    # Legacy (no prefix)
    legacy = conn.execute(
        "SELECT COUNT(*) FROM vector_chunks WHERE source NOT LIKE '%:%'"
    ).fetchone()[0]
    if legacy:
        print(f"    {'(legacy)':20s} {legacy:4d} chunks")

    # By domain
    print("\n  By domain:")
    rows = conn.execute(
        "SELECT COALESCE(NULLIF(domain, ''), '(blank)'), COUNT(*) "
        "FROM vector_chunks GROUP BY domain ORDER BY COUNT(*) DESC"
    ).fetchall()
    for domain, cnt in rows:
        print(f"    {domain:20s} {cnt:4d} chunks")

    # Harvest log
    try:
        h_total = conn.execute("SELECT COUNT(*) FROM harvest_log").fetchone()[0]
        if h_total > 0:
            print(f"\n  Harvest log ({h_total} entries):")
            gates = conn.execute(
                "SELECT gate_passed, COUNT(*) FROM harvest_log GROUP BY gate_passed ORDER BY COUNT(*) DESC"
            ).fetchall()
            for gate, cnt in gates:
                print(f"    {gate:30s} {cnt:4d}")
    except sqlite3.OperationalError:
        pass

    conn.close()
    print()


def cleanup() -> None:
    """Archive stale chunks based on chunk_health verdicts."""
    conn = _init_db()
    try:
        archived = conn.execute(
            "SELECT COUNT(*) FROM chunk_health WHERE verdict = 'archive'"
        ).fetchone()[0]
        print(f"[cleanup] {archived} chunks with 'archive' verdict")
        if archived > 0:
            print(
                "[cleanup] Run chunk_freshness_reviewer.py --all first to populate chunk_health"
            )
    except sqlite3.OperationalError:
        print(
            "[cleanup] chunk_health table not found — run chunk_freshness_reviewer.py first"
        )
    conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="DQ Knowledge Harvester v2")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--harvest", action="store_true", help="Harvest from academic sources"
    )
    group.add_argument("--ingest", metavar="FILE", help="Ingest a local file")
    group.add_argument(
        "--status", action="store_true", help="Show knowledge base status"
    )
    group.add_argument("--cleanup", action="store_true", help="Archive stale chunks")

    parser.add_argument("--domain", help="Target domain (e.g. formal_sciences)")
    parser.add_argument("--project", help="Project tag for --ingest (e.g. auto-report)")
    parser.add_argument("--query", help="Direct search query for --harvest")
    parser.add_argument("--max", type=int, default=10, help="Max papers to process")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be harvested"
    )

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.cleanup:
        cleanup()
    elif args.harvest:
        stats = harvest(
            target_domain=args.domain,
            query=args.query,
            max_papers=args.max,
            dry_run=args.dry_run,
        )
        print(f"\n[DONE] {stats}")
    elif args.ingest:
        stats = ingest_file(
            args.ingest, domain=args.domain or "", project=args.project or ""
        )
        print(f"\n[DONE] {stats}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
