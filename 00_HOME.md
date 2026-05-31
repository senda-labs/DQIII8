---
tags: [dqiii8, hub, moc]
project: dqiii8
server: netcup
status: active
updated: 2026-05-29
---
# DQIII8 — Mapa de Contenido

> Motor autónomo de orquestación multi-agente. Ubuntu VPS, SSH-only.
> UI principal: Telegram `@JARVISCONTROL3BOT` · CLI: `j cc` / `j loop` / `j status`

---

## Nodos Centrales

| Documento | Propósito |
|-----------|-----------|
| [[README]] | Guía pública: instalación, arquitectura, quick start |
| [[CLAUDE]] | Kernel operacional: routing tiers, reglas, system map |
| [[bin/README\|Catálogo de Scripts (bin/)]] | Inventario de los ~58 scripts activos y 21 archivados |
| [[tasks/FULL_SYSTEM_MAP\|Mapa Completo del Sistema]] | Snapshot detallado: pipeline, DB, hooks, crontab (§1–§15) |
| [[docs/architecture_decision_context_efficiency\|ADR-001: Eficiencia de Contexto]] | Decisión arquitectónica clave: por qué se consolidaron las reglas |
| [[docs/DQIII8_PLUGIN_DESIGN\|Diseño del Plugin MCP]] | Hoja de ruta: DQIII8 como plugin de Claude Code |
| [[skills-registry/INDEX\|Registro de Skills]] | 9 skills activas disponibles |

---

## Documentación y Referencia

- [[CONTRIBUTING]] — Guía de contribución, estilo de código y requisitos de PR
- [[PRIVACY]] — Política de privacidad (telemetría opt-in, desactivada por defecto)
- [[docs/CHANGELOG\|Changelog v0.1.0-beta]] — Historial de versiones y limitaciones conocidas
- [[docs/CHECKPOINT_2026-03-29\|Checkpoint 2026-03-29]] — Snapshot de estado del sistema: 80.3/100 HEALTHY

---

## Proyectos Activos (`my-projects/`)

- [[my-projects/ANOVA-PLAN-v2\|Plan Maestro ANOVA-Reports]] — Arquitectura y roadmap del sistema de informes
- [[my-projects/intl-reports/PROJECT\|intl-reports]] — Pipeline de informes de internacionalización (DOCX, ~50 págs/empresa)
- [[my-projects/content-automation/PROJECT\|content-automation]] — Pipeline de video faceless (8-stage CIP v2)
- [[my-projects/hult-finance/PROJECT\|hult-finance]] — Modelo financiero Hult IBS (completado)

---

## Objetivos (`objectives/`)

- [[objectives/active/OBJ-TEST-001\|OBJ-TEST-001: Verificar JAL-v3]] — Objetivo activo de verificación del framework JAL-v3

---

## Skills & Capacidades (`skills-registry/`)

- [[skills-registry/INDEX\|Índice de Skills]] — Catálogo completo de skills con estado (activa / deprecada)
- [[skills-registry/README\|Guía del Directorio]] — Estructura, cómo crear y cargar skills personalizadas

---

_Este archivo es el punto de entrada del vault. Para el mapa técnico completo y anotado del sistema en producción, ver [[tasks/FULL_SYSTEM_MAP|Full System Map]]._

---

## Infraestructura & Servidores

| Servidor | Estado | Nota |
|----------|--------|------|
| [[server-netcup]] | **activo** | Debian 13 · 16 GB · 8 vCores · alias `netcup` |
| [[server-hostinger]] | legacy | Ubuntu 24.04 · 8 GB · alias `serv` · convivencia paralela hasta ~2026-06-05 |

---

## Hubs de Proyecto (INDEX)

> Links a las notas índice de cada proyecto. Cada INDEX enlaza arriba a este hub y abajo a sus docs internos.

- [[my-projects/intl-reports/INDEX|intl-reports INDEX]] — pipeline activo de informes NEXO
- [[my-projects/pokemon-genesis-chaos/INDEX|pokemon-genesis-chaos INDEX]] — fangame Pokémon Essentials v21.1
- [[my-projects/content-automation/INDEX|content-automation INDEX]] — pipeline vídeo faceless
- [[my-projects/accounting-erp/INDEX|accounting-erp INDEX]] — ERP contable autónomo PGC 2007
- [[my-projects/ouroboros-q-eml/INDEX|ouroboros-q-eml INDEX]] — motor EML cuántico/hipercomplex (Phase 0A)
- [[my-projects/automatic-nutrition/INDEX|automatic-nutrition INDEX]] — generador de dietas

---

## Sesiones

Última sesión activa: `sessions/SESSION-YYYYMMDD-{servidor}.md` (leer al arrancar)
Histórico Hostinger: `sessions/YYYY-MM-DD_session_N.md`
