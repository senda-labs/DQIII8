#!/usr/bin/env python3
"""
JARVIS Memory Manager
Memoria persistente entre sesiones con mem0 + fallback SQLite (vault_memory).

Uso CLI:
  python3 bin/memory_manager.py add <session_id> <project> "<content>"
  python3 bin/memory_manager.py search <project> "<query>" [top_k]
  python3 bin/memory_manager.py semantic <project> "<query>" [top_k]
  python3 bin/memory_manager.py link <source_id> <target_id> <type>
  python3 bin/memory_manager.py related <memory_id>
  python3 bin/memory_manager.py decay
  python3 bin/memory_manager.py export [project]
  python3 bin/memory_manager.py import <file.json>
  python3 bin/memory_manager.py migrate
"""

import sys
import json
import sqlite3
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime

JARVIS_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"

# ── Embedding ──────────────────────────────────────────────────────
_OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
_EMBED_MODEL = "nomic-embed-text"

# Decay rates por scope (factor diario multiplicativo)
DECAY_RATES = {
    "session": 0.90,  # pierde 10%/día
    "project": 0.99,  # pierde 1%/día
    "system": 1.00,  # permanente
}

VALID_SCOPES = ("session", "project", "system")
VALID_LINK_TYPES = ("related_to", "contradicts", "supersedes", "prerequisite", "derived_from")


def _get_nomic_embedding(text: str) -> list[float] | None:
    """Genera embedding nomic-embed-text vía Ollama. Devuelve None si no disponible."""
    payload = json.dumps({"model": _EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        _OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosemgrep
            data = json.loads(resp.read())
            return data.get("embedding")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x**2 for x in a) ** 0.5
    nb = sum(x**2 for x in b) ** 0.5
    return dot / (na * nb + 1e-9)


# ── mem0 config: Ollama embeddings + qdrant local ──────────────────
_MEM0_CONFIG = {
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "qwen2.5-coder:7b",
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text",
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "jarvis_memories",
            "path": str(JARVIS_ROOT / "database" / "qdrant"),
        },
    },
}

_mem0_client = None
_mem0_available = None  # None = no comprobado aún

# Suprimir el traceback de qdrant al shutdown
import atexit
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)


def _get_mem0():
    """Inicializa mem0 con timeout. Devuelve cliente o None."""
    global _mem0_client, _mem0_available

    if _mem0_available is False:
        return None
    if _mem0_client is not None:
        return _mem0_client

    try:
        from mem0 import Memory

        _mem0_client = Memory.from_config(_MEM0_CONFIG)
        _mem0_available = True
        return _mem0_client
    except Exception as e:
        _mem0_available = False
        return None


# ── SQLite fallback ────────────────────────────────────────────────


def _db_add(session_id: str, project: str, content: str) -> bool:
    """Guarda en vault_memory. Usa entry_type='checkpoint' (válido en CHECK constraint)."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        conn.execute(
            """
            INSERT INTO vault_memory (subject, predicate, object, entry_type, project, last_seen)
            VALUES (?, 'recuerda', ?, 'checkpoint', ?, ?)
            ON CONFLICT(subject, predicate, object) DO UPDATE SET
                last_seen = excluded.last_seen,
                times_seen = times_seen + 1
            """,
            (session_id, content, project, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _db_search(project: str, query: str, top_k: int = 10) -> list[str]:
    """Búsqueda por palabras clave en vault_memory."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        terms = query.split()[:5]  # máximo 5 términos
        conditions = " OR ".join(["object LIKE ?" for _ in terms])
        params = [f"%{t}%" for t in terms] + [project, top_k]
        # `conditions` is built as "object LIKE ? OR object LIKE ? ..." — only
        # safe ? placeholders; no user data appears in the SQL structure.
        query = (
            "SELECT object FROM vault_memory"
            " WHERE (" + conditions + ")"
            " AND (project = ? OR project = '')"
            " AND entry_type IN ('session_memory', 'lesson', 'checkpoint', 'project_state')"
            " ORDER BY last_seen DESC"
            " LIMIT ?"
        )
        rows = conn.execute(query, params).fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


# ── API pública ────────────────────────────────────────────────────


def add_memory(session_id: str, project: str, content: str) -> dict:
    """
    Guarda una memoria.
    Intenta mem0 primero; si falla o no está disponible, usa vault_memory.
    """
    m = _get_mem0()
    if m is not None:
        try:
            result = m.add(
                content,
                user_id=project,
                metadata={"session_id": session_id, "project": project},
            )
            return {"backend": "mem0", "ok": True, "result": str(result)}
        except Exception as e:
            pass  # fallback silencioso

    ok = _db_add(session_id, project, content)
    return {"backend": "sqlite", "ok": ok}


def search_memories(project: str, query: str, top_k: int = 10) -> list[str]:
    """
    Recupera memorias relevantes.
    Intenta mem0 primero (timeout 2s); si falla, usa vault_memory.
    """
    m = _get_mem0()
    if m is not None:
        try:
            import signal

            def _timeout_handler(signum, frame):
                raise TimeoutError

            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(2)
            try:
                results = m.search(query, user_id=project, limit=top_k)
                signal.alarm(0)
                memories = results.get("results", results) if isinstance(results, dict) else results
                return [r.get("memory", str(r)) for r in memories if r]
            finally:
                signal.alarm(0)
        except (TimeoutError, Exception):
            pass  # fallback silencioso

    results = _db_search(project, query, top_k)
    if results:
        try:
            _conn = sqlite3.connect(str(DB_PATH), timeout=3)
            _now = datetime.now().isoformat()
            _terms = query.split()[:5]
            _conditions = " OR ".join(["object LIKE ?" for _ in _terms])
            _params = [f"%{t}%" for t in _terms] + [project]
            _conn.execute(
                "UPDATE vault_memory SET last_accessed=?, access_count=COALESCE(access_count,0)+1"
                " WHERE (" + _conditions + ") AND (project = ? OR project = '')",
                [_now] + _params,
            )
            _conn.commit()
            _conn.close()
        except Exception:
            pass
    return results


# ── vault_memory v2 — nuevas funciones ────────────────────────────


def migrate_vault_memory() -> dict:
    """
    Migra vault_memory al esquema v2:
    - Añade columnas: scope, embedding, transferable
    - Crea tabla memory_links
    - Actualiza scope para filas existentes según entry_type
    """
    if not DB_PATH.exists():
        return {"ok": False, "error": "DB not found"}

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    changes: list[str] = []

    # Añadir columnas nuevas (ignorar si ya existen)
    for col_sql in [
        "ALTER TABLE vault_memory ADD COLUMN scope TEXT DEFAULT 'session'",
        "ALTER TABLE vault_memory ADD COLUMN embedding BLOB",
        "ALTER TABLE vault_memory ADD COLUMN transferable INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(col_sql)
            changes.append(col_sql.split("ADD COLUMN")[1].strip().split()[0])
        except sqlite3.OperationalError:
            pass  # columna ya existe

    # Tabla memory_links
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   INTEGER NOT NULL REFERENCES vault_memory(id) ON DELETE CASCADE,
            target_id   INTEGER NOT NULL REFERENCES vault_memory(id) ON DELETE CASCADE,
            link_type   TEXT    NOT NULL DEFAULT 'related_to',
            strength    REAL    DEFAULT 1.0,
            created_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(source_id, target_id, link_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_links_source ON memory_links (source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_links_target ON memory_links (target_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_scope ON vault_memory (scope)")
    changes.append("memory_links table")

    # Migrar scope según entry_type
    conn.execute("""
        UPDATE vault_memory SET scope = CASE
            WHEN entry_type IN ('lesson', 'adr')   THEN 'system'
            WHEN entry_type = 'project_state'       THEN 'project'
            ELSE 'session'
        END
        WHERE scope = 'session' OR scope IS NULL
    """)

    # Marcar lessons y ADRs como transferables
    conn.execute("""
        UPDATE vault_memory SET transferable = 1
        WHERE entry_type IN ('lesson', 'adr') AND transferable = 0
    """)

    conn.commit()
    conn.close()
    return {"ok": True, "columns_added": changes}


def store_with_embedding(
    session_id: str,
    project: str,
    content: str,
    scope: str = "session",
    transferable: bool = False,
) -> dict:
    """Guarda en vault_memory con embedding nomic-embed-text si Ollama disponible."""
    if scope not in VALID_SCOPES:
        scope = "session"

    vec = _get_nomic_embedding(content)
    embedding_blob = _pack_vec(vec) if vec else None

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        conn.execute(
            """
            INSERT INTO vault_memory
                (subject, predicate, object, entry_type, project, last_seen,
                 scope, embedding, transferable)
            VALUES (?, 'recuerda', ?, 'checkpoint', ?, ?, ?, ?, ?)
            ON CONFLICT(subject, predicate, object) DO UPDATE SET
                last_seen   = excluded.last_seen,
                times_seen  = times_seen + 1,
                scope       = excluded.scope,
                embedding   = COALESCE(excluded.embedding, embedding),
                transferable= excluded.transferable
            """,
            (
                session_id,
                content,
                project,
                datetime.now().isoformat(),
                scope,
                embedding_blob,
                1 if transferable else 0,
            ),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "embedded": vec is not None, "scope": scope}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_semantic(project: str, query: str, top_k: int = 10) -> list[dict]:
    """
    Búsqueda semántica en vault_memory usando embeddings nomic-embed-text.
    Fallback a búsqueda por keywords si Ollama no disponible.
    """
    query_vec = _get_nomic_embedding(query)

    if not DB_PATH.exists():
        return []

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        rows = conn.execute(
            """
            SELECT id, subject, object, project, scope, confidence, embedding
            FROM vault_memory
            WHERE (project = ? OR project = '' OR ? = '')
              AND entry_type IN ('lesson', 'checkpoint', 'project_state', 'adr')
            ORDER BY last_seen DESC
            LIMIT 200
            """,
            (project, project),
        ).fetchall()
        conn.close()
    except Exception:
        return []

    if query_vec:
        scored: list[tuple[float, dict]] = []
        for row_id, subject, obj, proj, scope, conf, emb_blob in rows:
            if emb_blob:
                row_vec = _unpack_vec(emb_blob)
                score = _cosine(query_vec, row_vec)
            else:
                # texto match fallback
                score = 0.1 if query.lower() in (obj or "").lower() else 0.0
            scored.append(
                (
                    score,
                    {
                        "id": row_id,
                        "subject": subject,
                        "content": obj,
                        "project": proj,
                        "scope": scope,
                        "confidence": conf,
                        "score": round(score, 4),
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]
    else:
        # Sin embeddings → keywords
        results = _db_search(project, query, top_k)
        return [{"content": r, "score": 0.0, "method": "keyword"} for r in results]


def link_memories(
    source_id: int, target_id: int, link_type: str = "related_to", strength: float = 1.0
) -> dict:
    """Crea un enlace bidireccional entre dos memorias."""
    if link_type not in VALID_LINK_TYPES:
        return {"ok": False, "error": f"link_type inválido: {link_type}. Usa: {VALID_LINK_TYPES}"}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        conn.execute(
            "INSERT OR IGNORE INTO memory_links (source_id, target_id, link_type, strength) VALUES (?,?,?,?)",
            (source_id, target_id, link_type, strength),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "source": source_id, "target": target_id, "type": link_type}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_related(memory_id: int, max_depth: int = 2) -> list[dict]:
    """Recorre el grafo de memory_links hasta max_depth saltos."""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        visited: set[int] = set()
        frontier = [memory_id]
        results: list[dict] = []

        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: list[int] = []
            placeholders = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"SELECT source_id, target_id, link_type, strength FROM memory_links"
                f" WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                frontier + frontier,
            ).fetchall()
            for src, tgt, ltype, strength in rows:
                neighbor = tgt if src in frontier else src
                if neighbor not in visited and neighbor != memory_id:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
                    mem = conn.execute(
                        "SELECT id, subject, object, scope, confidence FROM vault_memory WHERE id=?",
                        (neighbor,),
                    ).fetchone()
                    if mem:
                        results.append(
                            {
                                "id": mem[0],
                                "subject": mem[1],
                                "content": mem[2],
                                "scope": mem[3],
                                "confidence": mem[4],
                                "link_type": ltype,
                                "strength": strength,
                            }
                        )
            frontier = next_frontier

        conn.close()
        return results
    except Exception:
        return []


def apply_decay(dry_run: bool = False) -> dict:
    """
    Aplica decay a vault_memory según scope.
    session: × 0.90/día · project: × 0.99/día · system: sin cambio.
    Retorna estadísticas.
    """
    if not DB_PATH.exists():
        return {"ok": False, "error": "DB not found"}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        stats: dict[str, int] = {}
        for scope, rate in DECAY_RATES.items():
            if rate >= 1.0:
                continue
            count = conn.execute(
                "SELECT COUNT(*) FROM vault_memory WHERE scope = ? AND decay_score > 0.01",
                (scope,),
            ).fetchone()[0]
            stats[scope] = count
            if not dry_run:
                conn.execute(
                    "UPDATE vault_memory SET decay_score = MAX(0.01, decay_score * ?) WHERE scope = ?",
                    (rate, scope),
                )
        if not dry_run:
            conn.commit()
        conn.close()
        return {"ok": True, "dry_run": dry_run, "updated": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def export_knowledge(project: str = "") -> dict:
    """Exporta memorias transferables como Knowledge Passport JSON."""
    if not DB_PATH.exists():
        return {"ok": False, "error": "DB not found"}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3)
        query = """
            SELECT id, subject, predicate, object, project, confidence,
                   entry_type, scope, created_at, last_seen
            FROM vault_memory
            WHERE transferable = 1
        """
        params: list = []
        if project:
            query += " AND (project = ? OR project = '' OR scope = 'system')"
            params.append(project)
        query += " ORDER BY confidence DESC, last_seen DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        memories = [
            {
                "id": r[0],
                "subject": r[1],
                "predicate": r[2],
                "object": r[3],
                "project": r[4],
                "confidence": r[5],
                "entry_type": r[6],
                "scope": r[7],
                "created_at": r[8],
                "last_seen": r[9],
            }
            for r in rows
        ]
        passport = {
            "version": "2.0",
            "exported_at": datetime.now().isoformat(),
            "source_project": project or "all",
            "count": len(memories),
            "memories": memories,
        }
        return {"ok": True, "passport": passport}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def import_knowledge(passport: dict, target_project: str = "") -> dict:
    """Importa un Knowledge Passport. Skips duplicates (ON CONFLICT IGNORE)."""
    memories = passport.get("memories", [])
    if not memories:
        return {"ok": False, "error": "passport vacío o sin memorias"}

    imported = 0
    skipped = 0
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        for m in memories:
            project = target_project or m.get("project", "")
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO vault_memory
                        (subject, predicate, object, project, confidence, entry_type,
                         scope, transferable, created_at, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        m.get("subject", "import"),
                        m.get("predicate", "recuerda"),
                        m.get("object", ""),
                        project,
                        m.get("confidence", 1.0),
                        m.get("entry_type", "lesson"),
                        m.get("scope", "system"),
                        m.get("created_at", datetime.now().isoformat()),
                        m.get("last_seen", datetime.now().isoformat()),
                    ),
                )
                imported += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
        conn.close()
        return {"ok": True, "imported": imported, "skipped": skipped}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "--help":
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "add":
        if len(args) < 4:
            print("Uso: memory_manager.py add <session_id> <project> '<content>'")
            sys.exit(1)
        session_id, project, content = args[1], args[2], args[3]
        result = add_memory(session_id, project, content)
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "search":
        if len(args) < 3:
            print("Uso: memory_manager.py search <project> '<query>' [top_k]")
            sys.exit(1)
        project = args[1]
        query = args[2]
        top_k = int(args[3]) if len(args) > 3 else 10
        memories = search_memories(project, query, top_k)
        if memories:
            for i, m in enumerate(memories, 1):
                print(f"{i}. {m}")
        else:
            print("(sin resultados)")

    elif cmd == "semantic":
        if len(args) < 3:
            print("Uso: memory_manager.py semantic <project> '<query>' [top_k]")
            sys.exit(1)
        project = args[1]
        query = args[2]
        top_k = int(args[3]) if len(args) > 3 else 10
        results = search_semantic(project, query, top_k)
        if results:
            for i, r in enumerate(results, 1):
                score = r.get("score", 0)
                print(
                    f"{i}. [{r.get('scope','?')}] (score={score:.3f}) {r.get('content','')[:120]}"
                )
        else:
            print("(sin resultados)")

    elif cmd == "link":
        if len(args) < 4:
            print("Uso: memory_manager.py link <source_id> <target_id> <type>")
            sys.exit(1)
        result = link_memories(int(args[1]), int(args[2]), args[3])
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "related":
        if len(args) < 2:
            print("Uso: memory_manager.py related <memory_id>")
            sys.exit(1)
        results = get_related(int(args[1]))
        if results:
            for r in results:
                print(f"  [{r['link_type']}] id={r['id']} {r.get('content','')[:100]}")
        else:
            print("(sin enlaces)")

    elif cmd == "decay":
        dry_run = "--dry-run" in args
        result = apply_decay(dry_run=dry_run)
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "export":
        project = args[1] if len(args) > 1 else ""
        result = export_knowledge(project)
        if result["ok"]:
            passport = result["passport"]
            out_path = JARVIS_ROOT / "tasks" / f"knowledge_passport_{project or 'all'}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(passport, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"✓ Exportadas {passport['count']} memorias → {out_path}")
        else:
            print(f"Error: {result.get('error')}")

    elif cmd == "import":
        if len(args) < 2:
            print("Uso: memory_manager.py import <file.json> [target_project]")
            sys.exit(1)
        file_path = Path(args[1])
        if not file_path.exists():
            print(f"Archivo no encontrado: {file_path}")
            sys.exit(1)
        passport = json.loads(file_path.read_text(encoding="utf-8"))
        target = args[2] if len(args) > 2 else ""
        result = import_knowledge(passport, target)
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "migrate":
        result = migrate_vault_memory()
        print(json.dumps(result, ensure_ascii=False))

    else:
        print(
            f"Comando desconocido: {cmd}. Usa add, search, semantic, link, related, decay, export, import, migrate."
        )
        sys.exit(1)
