---
name: proyecto
description: Declara el proyecto activo (scope global) para atribucion de coste/horas en agent_actions. Sin argumento, muestra el proyecto actual.
allowed_tools: ["Bash"]
---

# /proyecto — Declarar Proyecto Activo

Escribe una fila abierta en `project_context` (scope `global`), fuente de verdad
que `resolve_project()` consulta desde los puntos de escritura de
`agent_actions` (`pre_tool_use.py`, `openrouter_wrapper.log_to_db()`,
`pal/engine.py`, y los hooks de sesion) cuando no hay `project=` explicito.

## Uso

```
/proyecto                    # muestra el proyecto activo (scope global)
/proyecto football-value     # declara football-value como proyecto activo
/proyecto fin                # cierra la declaracion (vuelve a resolver por cwd/dqiii8-core)
```

Proyectos validos: cualquier directorio en `my-projects/` + `dqiii8-core`.
`/proyecto <nombre-invalido>` falla con la lista de proyectos conocidos.

`/hora inicio` sin argumento usa el proyecto resuelto por este comando en vez
de requerir el nombre explicito cada vez.

## Implementacion

Mapeo de argumentos: sin args -> `get`; `fin` -> `end`; cualquier otra cosa -> `set <arg>`.

```bash
cd /root/dqiii8
case "$1" in
  "") python3 bin/tools/project_ctl.py get ;;
  fin) python3 bin/tools/project_ctl.py end ;;
  *) python3 bin/tools/project_ctl.py set "$1" ;;
esac
```

## Notas DQIII8

- Version Telegram equivalente: `/proyecto` en `dqiii8_bot.py` (mismo `project_context`, `declared_by='telegram'`).
- Declarar via CLI en una sesion Claude Code no persiste automaticamente para
  otras sesiones/procesos hasta que estos re-consulten la DB via
  `resolve_project()` (`bin/core/project_context.py`) — no existe cache de
  entorno entre hooks: cada hook corre en su propio subproceso, asi que un
  `os.environ` escrito por uno nunca es visible para otro (Opus review
  P2-5, 2026-08-13, elimino el intento previo de cache via `DQIII8_PROJECT`).
