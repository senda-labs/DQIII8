---
name: mode
description: Activa un modo de trabajo para JARVIS. Opciones: analyst | coder | creative. El modo persiste hasta fin de sesion o reinicio del VPS.
allowed_tools: ["Bash"]
---

# /mode — Activar Modo de Trabajo

Escribe el modo en `/tmp/jarvis_mode.txt`. El hook `session_start.py` lo lee
al inicio de cada sesion e inyecta las instrucciones de comportamiento correspondientes.

## Uso

```
/mode coder
/mode analyst
/mode creative
/mode status
```

## Modos disponibles

| Modo | Foco | Estilo |
|------|------|--------|
| `coder` | Implementacion y correctitud | Codigo primero, prosa minima, Black siempre, show diffs |
| `analyst` | Datos, metricas, outputs estructurados | Tablas, verificar numeros, sin especulacion |
| `creative` | Narrativa, exploracion, alternativas | Long-form, espanol literario, sin formato tecnico |

Sin modo activo: comportamiento estandar neutro (hereda del proyecto activo).

## Implementacion

```bash
python3 -c "
import sys
from pathlib import Path

MODE_FILE = Path('/tmp/jarvis_mode.txt')
VALID_MODES = {'coder', 'analyst', 'creative'}

args = sys.argv[1:]
if not args or args[0] == 'status':
    current = MODE_FILE.read_text(encoding='utf-8').strip() if MODE_FILE.exists() else 'neutro'
    print(f'Modo activo: {current}')
    sys.exit(0)

mode = args[0].lower()
if mode not in VALID_MODES:
    print(f'Modo invalido: {mode!r}')
    print(f'Opciones: analyst | coder | creative')
    sys.exit(1)

MODE_FILE.write_text(mode, encoding='utf-8')
print(f'Modo activado: {mode}')
print('Persiste hasta fin de sesion (/mode status para verificar)')
" "$@"
```

## Notas JARVIS

- El modo se inyecta via `session_start.py` en el bloque JARVIS inicial
- `/tmp/jarvis_mode.txt` se borra al reiniciar el VPS (por diseno — no persiste entre reinicios)
- Para persistir entre reinicios: set `JARVIS_MODE=[modo]` en `.env`
- Cambiar modo en mitad de sesion no afecta el contexto actual — solo la siguiente sesion
- Definido en CLAUDE.md § Personality Modes
