---
name: mode
description: Activa un modo de trabajo para DQIII8. Opciones: analyst | coder | creative. El modo persiste hasta fin de sesion o reinicio del VPS.
command: /mode
allowed-tools: [Bash]
user-invocable: true
---

# /mode — Activar Modo de Trabajo

Escribe el modo en `var/dqiii8_mode.conf`. El hook `session_start.py` lo lee
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
import os, sys
from pathlib import Path

ROOT = Path(os.environ.get('DQIII8_ROOT', '/root/dqiii8'))
MODE_FILE = ROOT / 'var' / 'dqiii8_mode.conf'
LEGACY_FILE = Path('/tmp/dqiii8_mode.txt')
VALID_MODES = {'coder', 'analyst', 'creative'}

def current_mode():
    env = os.environ.get('DQIII8_MODE', '').strip().lower()
    if env in VALID_MODES:
        return f'{env} (via DQIII8_MODE env var — tiene prioridad sobre el fichero)'
    for path in (MODE_FILE, LEGACY_FILE):
        try:
            if path.exists():
                value = path.read_text(encoding='utf-8').strip()
                if value:
                    return f'{value} ({path})'
        except OSError:
            pass
    return 'neutro'

args = sys.argv[1:]
if not args or args[0] == 'status':
    print(f'Modo activo: {current_mode()}')
    sys.exit(0)

mode = args[0].lower()
if mode not in VALID_MODES:
    print(f'Modo invalido: {mode!r}')
    print('Opciones: analyst | coder | creative')
    sys.exit(1)

MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
MODE_FILE.write_text(mode + chr(10), encoding='utf-8')
print(f'Modo activado: {mode} -> {MODE_FILE}')
print('Persiste entre sesiones y reinicios (/mode status para verificar)')
" "$@"
```

## Notas DQIII8

- El modo se inyecta via `session_start.py` en el bloque DQIII8 inicial
- **Precedencia de lectura** (`session_start.py`, corregido 2026-08-17):
  `DQIII8_MODE` (env, **solo si su valor es `coder`/`analyst`/`creative`**) →
  `var/dqiii8_mode.conf` → `/tmp/dqiii8_mode.txt` (legacy). La validacion contra
  `_MODE_BEHAVIORS` es lo que evita que un `DQIII8_MODE=autonomous` (vocabulario de
  `permission_analyzer.py`) se interprete como estilo de escritura.
- `var/dqiii8_mode.conf` **sí persiste entre reinicios**; `var/` esta gitignorado,
  asi que el modo nunca se commitea
- **NUNCA escribir `DQIII8_MODE` en `.env`.** `.env` esta en `BLOCKED_PATHS`
  (`permission_analyzer.py`) — cualquier escritura se deniega — y ademas `DQIII8_MODE`
  como variable de entorno tiene un consumidor distinto (`permission_analyzer.py` la lee
  para el fast-path autonomo). Escribir el modo de personalidad ahi colisionaria con el
  control de permisos. El fichero `var/dqiii8_mode.conf` existe precisamente para separar
  ambos usos.
- Cambiar modo en mitad de sesion no afecta el contexto actual — solo la siguiente sesion
- Las definiciones de comportamiento por modo viven en `_MODE_BEHAVIORS`
  (`.claude/hooks/session_start.py`) y en la tabla de arriba
