# Windows / Cross-Platform Paths — DQIII8 Lessons

## Core Rule

ALWAYS use `pathlib.Path()`. NEVER concatenate strings for paths.

```python
# CORRECT
from pathlib import Path
output = Path("$JARVIS_ROOT/tasks/results") / "output.mp4"
ffmpeg_path = output.resolve().as_posix()

# INCORRECT
output = "$JARVIS_ROOT/tasks/results" + "/" + "output.mp4"
```

## FFmpeg and Paths with Spaces

Problem: paths with spaces break FFmpeg in `-vf` filters.
Solution: `Path(...).resolve().as_posix()` gives absolute path with forward slashes.

```python
# CORRECT — no quotes in filter when using subprocess list form
abs_path = Path(subtitle_file).resolve().as_posix()
ffmpeg_cmd = [
    "ffmpeg", "-i", input_video,
    "-vf", f"ass={abs_path}",   # no quotes around the path
    output_video
]

# INCORRECT — quotes break filter lookup
ffmpeg_cmd = ["ffmpeg", "-vf", f"ass='{abs_path}'"]
```

Lesson: [2026-03-09] [windows-path] Paths with spaces break FFmpeg →
use Path().as_posix()

## Colons on Windows (portability)

On Windows, paths have `C:\` → the colon conflicts with FFmpeg filters.
Escape: `path.replace(":", "\\:")` — not needed on Linux but keep for
portability if the code may run on Windows.

```python
def safe_ffmpeg_path(p: Path) -> str:
    """Safe path for use in FFmpeg filters (cross-platform)."""
    posix = p.resolve().as_posix()
    # On Windows: escape colon in drive letter only
    if ":" in posix[:3]:  # only drive letter, not other colons
        posix = posix.replace(":", "\\:", 1)
    return posix
```

## Encoding in open()

ALWAYS specify encoding="utf-8":

```python
# CORRECT
with open(filepath, encoding="utf-8") as f:
    content = f.read()

# INCORRECT — encoding depends on system (fails on Windows cp1252)
with open(filepath) as f:
    content = f.read()
```

## Paths in subprocess

```python
# CORRECT — use str() to convert Path to string in args
subprocess.run(["python3", str(script_path), arg1], check=True)

# For cwd as well
subprocess.run(cmd, cwd=str(working_dir), check=True)
```

## Relative vs. Absolute Paths

In DQIII8 scripts: always use absolute paths from JARVIS_ROOT.

```python
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
TASKS_DIR = JARVIS_ROOT / "tasks" / "results"
AGENTS_DIR = JARVIS_ROOT / ".claude" / "agents"

# For scripts called from different cwd:
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent  # bin/ → project root
```

## Validation Patterns

```python
def validate_input_file(filepath: str | Path) -> Path:
    p = Path(filepath).resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if not p.is_file():
        raise ValueError(f"Not a file: {p}")
    return p
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| FileNotFoundError with correct path | Extra quotes in string | Use Path() and strip() |
| FFmpeg filter `ass=` can't find file | Quotes in filter path | `f"ass={path}"` without quotes |
| UnicodeDecodeError in open() | Encoding not specified | Add `encoding="utf-8"` |
| OSError on Windows | Mixed backslashes | `.as_posix()` normalizes |
