# DQIII8 — Python Standards

> Extends python/coding-style.md with DQIII8-specific conventions.

- **Formatter**: Black (runs automatically via PostToolUse hook — do not run manually).
- **Paths**: always use `pathlib.Path()`. Never concatenate strings for paths. Use `.as_posix()` for Windows compat.
- **Encoding**: always specify `encoding="utf-8"` in `open()`.
- **Async**: use asyncio for I/O-bound tasks (API calls, file batches). No async for CPU-only work.
- **Imports**: stdlib → third-party → local. One blank line between groups.
