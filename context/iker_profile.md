---
title: Iker — Perfil del Usuario
tags: [context, profile, user]
last_updated: 2026-03-12
read_only: true
---

# Iker — Perfil

## Identidad
Iker Martínez. MBA student en Hult International Business School.
Emprendedor técnico. Builder de sistemas de automatización de contenido.

## Infraestructura
- **VPS:** Ubuntu 24.04 · IP 76.13.40.235
- **Sistema JARVIS:** `/root/jarvis/` — orquestador Claude Code con hooks, agentes, routing
- **Proyecto principal:** `/root/content-automation-faceless/` — pipeline de vídeo faceless
- **Repo GitHub:** github.com/ikermartiinsv-eng/jarvis

## Stack técnico
- **Lenguajes:** Python (principal), SQL, bash
- **Frameworks:** FastAPI, MoviePy, FFmpeg, Telegram Bot PTB v20
- **IA/Audio:** Claude API (Sonnet 4.6), Groq (Llama 3.3), ElevenLabs, Ollama local (qwen2.5-coder)
- **DB:** SQLite (jarvis_metrics.db, asset_library.db)
- **Imágenes:** Pixabay, Wikimedia, NASA APOD, Flickr CC, Pollinations (IA)
- **Despliegue:** tmux sessions, git push → GitHub → Obsidian sync

## Proyectos activos

| Proyecto | Estado | Descripción |
|----------|--------|-------------|
| [[content-automation]] | 🟢 Activo | Pipeline vídeo faceless YouTube/TikTok/IG |
| [[hult-finance]] | 🟡 Activo | Corporate Finance MBA — análisis, WACC, DCF |
| [[leyendas-del-este]] | 🔵 Pausado | Novela xianxia en español |
| [[jarvis-core]] | 🟢 Activo | Infraestructura del sistema JARVIS |

## Canales YouTube
Ver [[youtube_channels]] para detalle completo.
- **Echoes of the Past** — historia
- **Primordial Economics** — economía
- **Tao & Thought** — filosofía
- **Football Chronicles** — fútbol
- **Sapiens Origins** — antropología

## Meta principal
Automatizar la producción de contenido faceless para monetizar YouTube.
Pipeline objetivo: tema → script (Groq) → TTS (ElevenLabs) → vídeo (PIL/MoviePy) → subtítulos → publicación automática.

## Idioma de trabajo
Español (Claude responde en español salvo que Iker use inglés)

## Preferencias de trabajo
- Respuestas concisas y directas
- Plan mode para tareas de 3+ pasos
- Sin emojis salvo que se pidan explícitamente
- Lecciones en `tasks/lessons.md` al corregir algo
