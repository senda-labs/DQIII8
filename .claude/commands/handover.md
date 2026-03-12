# /handover — Session Handover Note

## Trigger
Usuario escribe `/handover` al final de una sesión de trabajo.

## Comportamiento

### 1. Recopilar información
- Determinar el proyecto activo: variable `JARVIS_PROJECT` o inferir del CWD
- Leer `projects/[proyecto].md` para el próximo paso actual
- Leer `tasks/lessons.md` (últimas 5 entradas, solo las de hoy)
- Ejecutar `git diff --stat HEAD` para listar archivos modificados

### 2. Generar `sessions/YYYY-MM-DD_session.md`

Usar la fecha actual (formato ISO). Si ya existe ese archivo del día, añadir sufijo `_2`, `_3`, etc.

```markdown
---
date: YYYY-MM-DD
time: HH:MM
project: [proyecto activo]
agent_used: claude-sonnet-4-6
session_id: [session_id si disponible]
---

# Sesión YYYY-MM-DD

## Qué hicimos
- [3-5 bullets concretos describiendo las tareas completadas]
- [Cada bullet: acción + archivo/módulo afectado + resultado]

## Archivos modificados
- `ruta/archivo.py` — [descripción del cambio]
- `ruta/otro.md` — [descripción del cambio]

## Próximo paso
[1 línea clara y accionable — debe coincidir con projects/[proyecto].md]

## Lecciones aprendidas
- [Solo si hubo correcciones o descubrimientos nuevos. Omitir sección si no hay.]
```

### 3. Actualizar `projects/[proyecto].md`
En la sección "Última sesión" (crearla si no existe), escribir:
```
**Última sesión:** YYYY-MM-DD — [1-liner resumen de la sesión]
```

### 4. Git push
```bash
git -C $JARVIS_ROOT add sessions/ projects/
git -C $JARVIS_ROOT commit -m "📝 session handover YYYY-MM-DD"
git -C $JARVIS_ROOT push origin main
```

### 5. Feedback al usuario
```
[HANDOVER] ✅ Sesión guardada en sessions/YYYY-MM-DD_session.md y pusheada a GitHub
```

## Notas
- Si git push falla (red, auth), informar pero NO bloquear — el archivo .md ya está guardado localmente
- Nunca incluir información sensible (API keys, passwords) en el handover
- Los archivos en `context/` son de referencia — NO los incluyas en la lista de archivos modificados salvo que el usuario los haya cambiado explícitamente
