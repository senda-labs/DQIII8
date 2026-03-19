# Windows / Cross-Platform Paths — Lecciones DQIII8

## Regla Fundamental

SIEMPRE usar `pathlib.Path()`. NUNCA concatenar strings para rutas.

```python
# CORRECTO
from pathlib import Path
output = Path("/root/dqiii8/tasks/results") / "output.mp4"
ffmpeg_path = output.resolve().as_posix()

# INCORRECTO
output = "/root/dqiii8/tasks/results" + "/" + "output.mp4"
```

## FFmpeg y Paths con Espacios

Problema: paths con espacios rompen FFmpeg en filtros `-vf`.
Solución: `Path(...).resolve().as_posix()` da ruta absoluta con forward slashes.

```python
# CORRECTO — sin comillas en filtro subprocess list form
abs_path = Path(subtitle_file).resolve().as_posix()
ffmpeg_cmd = [
    "ffmpeg", "-i", input_video,
    "-vf", f"ass={abs_path}",   # sin comillas alrededor del path
    output_video
]

# INCORRECTO — comillas rompen el lookup del filtro
ffmpeg_cmd = ["ffmpeg", "-vf", f"ass='{abs_path}'"]
```

Lección: [2026-03-09] [windows-path] Rutas con espacios rompen FFmpeg →
usar Path().as_posix()

## Colons en Windows (portabilidad)

En Windows, los paths tienen `C:\` → el colon conflicta con filtros FFmpeg.
Escape: `path.replace(":", "\\:")` — no necesario en Linux pero mantener
para portabilidad si el código puede ejecutarse en Windows.

```python
def safe_ffmpeg_path(p: Path) -> str:
    """Path seguro para usar en filtros FFmpeg (cross-platform)."""
    posix = p.resolve().as_posix()
    # En Windows: escapar colon del drive letter
    if ":" in posix[:3]:  # solo drive letter, no otros colons
        posix = posix.replace(":", "\\:", 1)
    return posix
```

## Encoding en open()

SIEMPRE especificar encoding="utf-8":

```python
# CORRECTO
with open(filepath, encoding="utf-8") as f:
    content = f.read()

# INCORRECTO — encoding depende del sistema (falla en Windows cp1252)
with open(filepath) as f:
    content = f.read()
```

## Paths en subprocess

```python
# CORRECTO — usar str() para convertir Path a string en args
subprocess.run(["python3", str(script_path), arg1], check=True)

# Para cwd también
subprocess.run(cmd, cwd=str(working_dir), check=True)
```

## Paths Relativos vs. Absolutos

En scripts DQIII8: usar siempre absolutos desde JARVIS_ROOT.

```python
JARVIS_ROOT = Path("/root/dqiii8")
TASKS_DIR = JARVIS_ROOT / "tasks" / "results"
AGENTS_DIR = JARVIS_ROOT / ".claude" / "agents"

# Para scripts que se llaman desde distintos cwd:
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent  # bin/ → dqiii8/
```

## Patrones de Validación

```python
def validate_input_file(filepath: str | Path) -> Path:
    p = Path(filepath).resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if not p.is_file():
        raise ValueError(f"Not a file: {p}")
    return p
```

## Errores Comunes

| Error | Causa | Fix |
|-------|-------|-----|
| FileNotFoundError con path correcto | Comillas extras en string | Usar Path() y strip() |
| FFmpeg filtro `ass=` no encuentra archivo | Comillas en path de filtro | `f"ass={path}"` sin comillas |
| UnicodeDecodeError en open() | Encoding no especificado | Añadir `encoding="utf-8"` |
| OSError en Windows | Backslashes mezclados | `.as_posix()` uniformiza |
