---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Standards (DQIII8)

## Formatting & linting
- **Black** auto-runs via PostToolUse hook — never run manually
- isort for imports, ruff for linting
- PEP 8 + type annotations on all function signatures

## DQIII8-specific conventions
- **Paths**: always `pathlib.Path()` — never string concatenation
- **Encoding**: always `encoding="utf-8"` in `open()`
- **Async**: asyncio for I/O-bound (API calls, file batches); no async for CPU-only
- **Imports**: stdlib → third-party → local, one blank line between groups
- **Logging**: use `logging` module — never `print()` in production code

## Immutability & structure
- Prefer `@dataclass(frozen=True)` / `NamedTuple` for value objects
- Functions < 50 lines, files < 800 lines
- No deep nesting (>4 levels)
- `Protocol` for duck-typed interfaces

## Security (Python-specific)
```python
import os
api_key = os.environ["API_KEY"]  # raises KeyError if missing — never default to ""
```
- No hardcoded secrets; use env vars
- `bandit -r src/` before committing security-sensitive modules
- Parameterized queries only — no string-format SQL

## Testing
- Framework: **pytest** + `pytest --cov=src --cov-report=term-missing`
- Mark tests: `@pytest.mark.unit`, `@pytest.mark.integration`
- Write test first (RED) → implement (GREEN) → refactor
- 80%+ coverage required
