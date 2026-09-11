# Contexto para modelos de IA — {{TITULO_PROYECTO}}

Este archivo existe para que, al abrir una sesión de Claude Code sobre este proyecto, el modelo
sepa en 30 segundos qué es lo importante — sin tener que leer todo el proyecto de arriba a abajo
cada vez. Menos contexto irrelevante = respuestas más rápidas, más baratas y más precisas.

## Leer primero (en este orden)

1. `README.md` — qué es el proyecto y para quién.
2. `PROJECT.md` — estado actual y próximos pasos.
3. Solo si hace falta detalle: `docs/ARCHITECTURE.md`.

## No repetir en cada sesión

- El objetivo del proyecto ya está en `README.md` — no lo reescribas en cada nota.
- El cliente y el responsable de cuenta ya están en el frontmatter de `README.md` — no los
  copies en cada archivo nuevo.

## Reglas específicas de este proyecto

{{REGLAS_ESPECIFICAS — p.ej. "nunca compartir cifras exactas de facturación fuera de 03-entregables/",
o vacío si no aplica ninguna todavía}}

## Al terminar una sesión

Actualiza `PROJECT.md` → Estado actual / Próximos pasos con lo que cambió. Así la siguiente
sesión (tuya o de otra persona) no empieza de cero.
