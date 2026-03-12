# /handover — Session Handover Note

## Trigger
Usuario escribe `/handover` al final de una sesión de trabajo.

## Comportamiento

Ejecuta el script de handover con una sola llamada:

```bash
python3 /root/jarvis/bin/handover.py
```

El script hace todo sin herramientas adicionales de Claude:
- Recoge archivos modificados via `git diff --stat HEAD`
- Lee `projects/[proyecto].md` para el próximo paso
- Lee `tasks/lessons.md` (entradas de hoy)
- Escribe `sessions/YYYY-MM-DD_session.md`
- Actualiza `projects/[proyecto].md` (sección "Ultima sesion")
- `git add sessions/ projects/` → commit → push origin master

## Invocación no-interactiva

```bash
claude --dangerously-skip-permissions -p "/handover"
```

## Notas
- Si git push falla (red/auth), el archivo .md queda guardado localmente — no bloquea
- Nunca incluir información sensible (API keys, passwords) en el handover
- Variable `JARVIS_PROJECT` controla el proyecto activo (default: `jarvis-core`)
