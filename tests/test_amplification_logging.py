"""tests/test_amplification_logging.py — A1/E1: amplification_log writes confidence/knowledge_used/success."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin" / "agents"))
sys.path.insert(0, str(ROOT / "bin" / "core"))


def test_log_amplification_writes_new_columns(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE amplification_log (
            id INTEGER PRIMARY KEY, created_at TEXT, original_prompt TEXT,
            amplified_prompt TEXT, action_detected TEXT, entity_detected TEXT,
            niche_detected TEXT, intent_pattern TEXT, top_domain TEXT,
            tier_selected INTEGER, elapsed_ms INTEGER,
            confidence REAL DEFAULT 0, knowledge_used INTEGER DEFAULT 0,
            subtask_count INTEGER DEFAULT 0, success INTEGER DEFAULT 1,
            routing_method TEXT DEFAULT 'single', active_centroids_count INTEGER DEFAULT 1,
            queued_centroids_count INTEGER DEFAULT 0, classification_ms REAL DEFAULT 0)
    """)
    conn.commit()
    conn.close()

    import intent_amplifier as ia

    class _Ctx:
        def __enter__(self):
            self.c = sqlite3.connect(db)
            return self.c
        def __exit__(self, *a):
            self.c.commit()
            self.c.close()

    monkeypatch.setattr(ia, "get_db", lambda: _Ctx())
    ia._log_amplification(
        original="p", amplified="a",
        decomp={"action": "debug", "entity": "X", "niche": ""},
        intent={"id": "debug", "score": 2, "tier": 1},
        domains=[{"domain": "applied_sciences", "score": 0.9}],
        tier=3, elapsed_ms=5, routing=None,
        chunks_injected=2, success=1,
    )
    row = sqlite3.connect(db).execute(
        "SELECT confidence, knowledge_used, success FROM amplification_log"
    ).fetchone()
    assert row is not None
    assert row[0] > 0          # confidence derived from intent score
    assert row[1] == 1         # knowledge_used: chunks_injected > 0
    assert row[2] == 1
