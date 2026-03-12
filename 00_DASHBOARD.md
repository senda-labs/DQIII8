---
title: JARVIS Dashboard
date_updated: 2026-03-12 12:16
week_number: W11 2026
tags: [dashboard, weekly]
---

# JARVIS Dashboard
**Actualizado:** 2026-03-12 · Semana W11
**VPS:** 76.13.40.235 · Ubuntu 24.04 · /root/jarvis/

---

## Estado de Proyectos

| Proyecto | Status | Último avance | Próximo paso |
|----------|--------|---------------|--------------|
| [[content-automation]] | 🟢 Activo | Fase 6A — TypographicRenderer con fuentes TTF reales | Fix subtítulos visibles en video final |
| [[hult-finance]] | 🟡 Activo | Análisis capital structure renovables europeas | Añadir scenario analysis |
| [[leyendas-del-este]] | 🔵 Pausado | Capítulo 1 revisado con feedback | Aplicar feedback e iniciar Cap. 2 |
| [[jarvis-core]] | 🟢 Activo | Fase 5.5 — Obsidian Brain + vault GitHub sync | Completar integración /handover + /weekly-review |

---

## Fases completadas (jarvis-core)

| Fase | Descripción | Estado |
|------|-------------|--------|
| Fase 1 | Infraestructura VPS + hooks básicos | ✅ |
| Fase 2 | ollama_wrapper + routing 3 niveles | ✅ |
| Fase 3.5 | OpenRouter wrapper + routing 4 niveles | ✅ |
| Fase 4 | Worktrees + auditor wiring | ✅ |
| Fase 5 | Auditor end-to-end (score 89/100) | ✅ |
| Fase 5.5 | Obsidian Brain + GitHub sync | 🔄 En progreso |
| Fase 6A | TypographicRenderer fuentes TTF | ✅ |

---

## Sesiones esta semana

> No hay sesiones registradas en `sessions/` aún — se generarán automáticamente via /handover

---

## Métricas (último audit)

| Métrica | Valor |
|---------|-------|
| Score audit | 89/100 🟢 HEALTHY |
| Fecha audit | 2026-03-11 |
| Acciones totales (7d) | 348 |
| Tasa de éxito | 96.6% |
| Agente más activo | claude-sonnet-4-6 (197 acciones) |
| Errores sin resolver | 0 |
| Próximo audit | 2026-03-18 |

---

## Tareas pendientes

> [!todo] content-automation
> - [ ] Fix subtítulos visibles en video final (FFmpeg -vf ass= path absoluto)
> - [ ] Imágenes cinematográficas para modo historian
> - [ ] Auto-publicación YouTube Shorts (OAuth2 ya configurado)
> - [ ] TikTok Content Posting API (pendiente aprobación)

> [!todo] hult-finance
> - [ ] Scenario analysis en análisis capital structure
> - [ ] Visualizaciones matplotlib para presentación Hult

> [!todo] leyendas-del-este
> - [ ] Aplicar feedback Capítulo 1
> - [ ] Borrador Capítulo 2

> [!todo] jarvis-core
> - [ ] Verificar wikilinks [[archivo]] en todos los .md
> - [ ] Configurar Obsidian Git plugin en PC para auto-pull
> - [ ] lessons_added en BD (fix stop.py ya implementado)

---

## Alertas activas

> [!warning] Subtítulos no visibles en video final
> `netflix_subtitle_generator.py` genera ASS correcto pero FFmpeg no los incrusta. Archivo: `professional_pipeline_v3.py` paso 7.

> [!info] Fase 5.5 en progreso
> Vault Obsidian estructurado. Pendiente: configurar Obsidian Git plugin en tu PC para sync automático desde GitHub.

---

## Contexto rápido

- [[iker_profile|Perfil Iker]] · [[youtube_channels|Canales YouTube]]
- Idioma: español · Modelo: claude-sonnet-4-6
- Bot Telegram: @AsistentAutomatorbot (tmux jarvis_bot)
