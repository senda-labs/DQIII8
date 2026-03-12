# JARVIS — Python Standards

> Extiende python/coding-style.md con convenciones específicas de JARVIS.

- **Formatter**: Black (corre automáticamente vía PostToolUse hook — no ejecutar manualmente).
- **Paths**: siempre `pathlib.Path()`. Nunca concatenación de strings para rutas. Usar `.as_posix()` para compat Windows.
- **Encoding**: especificar siempre `encoding="utf-8"` en `open()`.
- **Async**: usar asyncio para tareas I/O-bound (API calls, batch de archivos). No async trabajo CPU puro.
- **Imports**: stdlib → third-party → local. Una línea en blanco entre grupos.
