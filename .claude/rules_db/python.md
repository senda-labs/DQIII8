# Python Standards (DQIII8)

Only what a competent model would get *wrong* about this repo. PEP 8, import ordering,
type annotations, `@dataclass(frozen=True)`, `Protocol` and the like are model-prior
knowledge and are not repeated here — this file is injected on every `.py` edit.

## DQIII8-specific conventions
- **Black auto-runs via a PostToolUse hook** — never run it manually, and don't reformat a
  file "to match" before the hook does. isort/ruff are the configured linters.
- **Paths**: always `pathlib.Path()` — never string concatenation
- **Encoding**: always `encoding="utf-8"` in `open()` / `read_text()` / `write_text()`
- **Async**: asyncio for I/O-bound (API calls, file batches); no async for CPU-only
- **Logging**: `logging` module — never `print()` in production code

## Security (Python-specific)
```python
import os
api_key = os.environ["API_KEY"]  # raises KeyError if missing — never default to ""
```
- No hardcoded secrets; env vars only — SSOT for this rule on the `.py` path.
- Parameterized queries only — no string-format SQL
- `bandit -r src/` before committing security-sensitive modules

## Testing
- Framework: **pytest** + `pytest --cov=src --cov-report=term-missing`; 80%+ coverage
- Mark tests: `@pytest.mark.unit`, `@pytest.mark.integration`
- Write test first (RED) → implement (GREEN) → refactor
