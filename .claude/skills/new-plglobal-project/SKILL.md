---
name: new-plglobal-project
description: Crea un proyecto nuevo en my-projects/ con documentación y estructura de carpetas en notación Obsidian, pensado para operadores sin experiencia técnica (Isabel, Mario). Úsalo cuando pidan "crear un proyecto nuevo", "empezar un caso nuevo de cliente" o similar.
---

# Crear un proyecto nuevo P&L Global

Objetivo: que alguien sin experiencia técnica termine con un proyecto tan bien estructurado como
`intl-reports` o `market-intel` — carpetas claras, documentación mínima pero suficiente, y
contexto pensado para que un modelo de IA trabaje bien en sesiones futuras.

## Pasos

1. Pregunta lo mínimo imprescindible si no te lo han dado ya: nombre del proyecto, cliente,
   responsable de cuenta (Isabel o Mario), objetivo en una frase, y sector si aplica.
2. Deriva un slug en minúsculas con guiones a partir del nombre (p.ej. "Estudio mercado México
   para Acme" → `estudio-mercado-mexico-acme`).
3. Copia la plantilla completa de `/root/dqiii8/templates/plglobal-project-obsidian/` a
   `/root/dqiii8/my-projects/<slug>/`, conservando la estructura de carpetas
   (`01-notas/`, `02-investigacion/`, `03-entregables/`, `docs/`).
4. Rellena los placeholders `{{...}}` en `README.md`, `PROJECT.md`, `docs/ARCHITECTURE.md` y en
   `docs/CONTEXT.md` — rellena ese scaffold recién copiado en el paso 3, no existe en este repo
   hasta ese punto — con la información real del paso 1. No dejes ningún `{{...}}` sin rellenar
   — si algo no se sabe todavía, escribe "por definir" en vez de dejar el placeholder.
5. Crea las carpetas vacías `01-notas/`, `02-investigacion/`, `03-entregables/` (con un `.gitkeep`
   si hace falta que no queden vacías).
6. Confirma al operador dónde está el proyecto y qué archivo mirar primero (`PROJECT.md`).

## Notas importantes

- El proyecto se crea con las credenciales del propio operador (Write/Edit corren con su UID de
  Linux), así que queda privado por defecto — nadie más lo ve hasta que se comparta explícitamente.
- Si el proyecto necesita ser visible también para el otro operador, dilo explícitamente al
  terminar: la forma correcta de compartirlo es `sudo /root/dqiii8/ops/plglobal/grant-project-access.sh <slug> ambos`,
  ejecutado por un administrador (root) — un operador no tiene permiso para concedérselo a sí
  mismo ni al otro.
- No inventes cifras, clientes ni cronogramas — deja "por definir" si el operador no lo ha dado.
- No repitas en `docs/CONTEXT.md` (el paso 4 lo rellena) información que ya está en
  `README.md`; el objetivo es que las sesiones de IA futuras lean poco y entiendan mucho.
