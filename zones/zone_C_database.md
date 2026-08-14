# Zone C — Database
> Updated: 2026-06-02

---

## What it covers
All SQLite databases, schema management, and database access patterns.

---

## Databases

| DB | Path | Size | Tables |
|---|---|---|---|
| Main | `database/dqiii8.db` | — | schema SSOT, incl. session_memory (2026-08-14) |
| Knowledge | `database/dqiii8_knowledge.db` | — | vector/chunks/metrics (renamed from dqiii8_metrics.db, 2026-08-14) |
| Schema source | `database/schema_v2.sql` | — | 65 defined |

**NEVER commit `*.db` files** — gitignored. Use `schema_v2.sql` for fresh installs.

---

## Key Access Files

| File | Role |
|---|---|
| `bin/core/db.py` | Singleton SQLite connection + context manager |
| `bin/core/db_security.py` | Secret scanner (API keys before commit) |
| `database/schema_v2.sql` | Canonical schema — source of truth for fresh installs |
| `var/` | Variable runtime data |

---

## Quick Inspection

```bash
sqlite3 database/dqiii8.db ".tables"
sqlite3 database/dqiii8.db ".schema {table}"
sqlite3 database/dqiii8_knowledge.db ".tables"

# Row count check
sqlite3 database/dqiii8.db "SELECT COUNT(*) FROM {table};"
```

---

## Mutation Rules

Before any DB write, read `.claude/rules/01_database_mutations.md`. Key constraints:
- Schema changes → update `schema_v2.sql` in the same commit
- Never DROP without explicit user confirmation
- Migrations must be idempotent (safe to re-run)

---

## Cross-zone Links
- Schema documentation → [[zone_F_knowledge]]
- DB accessed by pipeline → [[zone_A_core_pipeline]]
