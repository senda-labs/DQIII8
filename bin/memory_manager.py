#!/usr/bin/env python3
"""
JARVIS Memory Manager
Memoria persistente entre sesiones con mem0 + fallback SQLite (vault_memory).

Uso CLI:
  python3 bin/memory_manager.py add <session_id> <project> "<content>"
  python3 bin/memory_manager.py search <project> "<query>" [top_k]
"""

import sys
import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime

JARVIS_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"

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

    else:
        print(f"Comando desconocido: {cmd}. Usa add o search.")
        sys.exit(1)
