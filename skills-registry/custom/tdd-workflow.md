---
name: tdd-workflow
description: Use this skill when writing new features or fixing bugs in JARVIS or content-automation-faceless. Enforces test-driven development with pytest — write test first, implement to pass, refactor.
origin: ECC/affaan-m (adaptado para JARVIS — pytest, pathlib, SQLite)
status: APROBADA
---

# TDD Workflow Skill

## When to Activate

- Adding a new function or class to `bin/`, `.claude/hooks/`, or `backend/`
- Fixing a bug (write a failing test that reproduces it first)
- Refactoring an existing module
- Before any commit touching more than 1 Python file

## Core Principles

1. **Tests BEFORE code** — Write the test, watch it fail, then implement
2. **Coverage target: 80%** — Check with `pytest --cov`
3. **Test types**: unit (functions), integration (DB + file I/O), smoke (CLI entry points)

## TDD Steps

### Step 1 — Write the failing test (RED)

```python
# tests/test_statusline.py
import pytest
from pathlib import Path
from bin.statusline import _print

def test_print_text_format():
    m = {"project": "jarvis-core", "session_min": 5, "actions": 10,
         "blocked": 1, "tokens": 4000, "audit_score": 82.0, "vault_facts": 28}
    # Should not raise; output contains project name
    import io, sys
    buf = io.StringIO()
    sys.stdout = buf
    _print(m, as_json=False)
    sys.stdout = sys.__stdout__
    assert "jarvis-core" in buf.getvalue()
    assert "Acciones: 10" in buf.getvalue()
```

Run to confirm it fails: `python3 -m pytest tests/test_statusline.py -x`

### Step 2 — Implement (GREEN)

Write the minimal implementation that makes the test pass.
No over-engineering. No extra features.

### Step 3 — Run tests (should pass)

```bash
python3 -m pytest tests/ -x -q
```

### Step 4 — Refactor (IMPROVE)

Clean up the implementation. Re-run tests after each change.

### Step 5 — Check coverage

```bash
python3 -m pytest tests/ --cov=bin --cov=.claude/hooks --cov-report=term-missing -q
```

Target: ≥ 80% for the module under test.

## JARVIS Test Patterns

### SQLite integration test (in-memory DB)

```python
import sqlite3, pytest

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE agent_actions (
        id INTEGER PRIMARY KEY, session_id TEXT,
        tokens_used INTEGER, blocked_by_hook INTEGER DEFAULT 0
    )""")
    conn.commit()
    yield conn
    conn.close()

def test_action_count(db):
    db.execute("INSERT INTO agent_actions(session_id, tokens_used) VALUES (?,?)", ("s1", 500))
    db.commit()
    row = db.execute("SELECT COUNT(*) FROM agent_actions WHERE session_id=?", ("s1",)).fetchone()
    assert row[0] == 1
```

### Pathlib / file test

```python
from pathlib import Path
import tempfile

def test_state_file_written(tmp_path):
    state_file = tmp_path / "precompact_state.json"
    state_file.write_text('{"session_id": "test"}', encoding="utf-8")
    data = __import__("json").loads(state_file.read_text(encoding="utf-8"))
    assert data["session_id"] == "test"
```

### CLI smoke test

```python
import subprocess, sys

def test_statusline_runs():
    result = subprocess.run(
        [sys.executable, "bin/statusline.py", "--json"],
        capture_output=True, text=True, cwd="/root/jarvis"
    )
    assert result.returncode == 0
    import json
    data = json.loads(result.stdout)
    assert "project" in data
```

## Common Mistakes to Avoid

| Wrong | Correct |
|-------|---------|
| Test implementation details (internal variable names) | Test observable behavior (output, DB state) |
| Test with real `/root/jarvis/database/jarvis_metrics.db` | Use `:memory:` or `tmp_path` fixture |
| `assert result == True` | `assert result is True` or just `assert result` |
| Giant test functions | One behavior per test function |

## File Organization

```
/root/jarvis/
  tests/
    test_statusline.py
    test_precompact.py
    test_permission_analyzer.py
    conftest.py          # shared fixtures (in-memory DB, tmp paths)
```

## Success Metrics

- All tests pass: `pytest tests/ -q`
- Coverage ≥ 80%: `pytest --cov --cov-fail-under=80`
- No test modifies real DB or real `.env`

## Related

- `verification-loop` — run after TDD to confirm all phases pass
- `security-review` — run on auth/input-handling code
