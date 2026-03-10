# content-automation — Estado del Proyecto
Última actualización: 2026-03-10

## Estado actual
Sistema de automatización de vídeo faceless. Pipeline: script viral → TTS (ElevenLabs) → vídeo Ken Burns (MoviePy) → subtítulos Netflix → export. Módulo de subtítulos recién refactorizado.

## Agentes asignados
- Principal: content-automator (Fase 3 — pendiente de añadir)
- Código: python-specialist
- Review: code-reviewer

## Skills activas
(ninguna aún — pendiente de sync en Fase 4)
Combo objetivo: video-pipeline, tts-elevenlabs, python-async

## Modelo preferido
local (qwen2.5-coder:3b) — 100% Ollama, $0 API

## Próximo paso
Revisar los 9 módulos core uno a uno antes de optimizar código interno.

## Lecciones específicas de este proyecto
- [2026-03-09] Rutas Windows con espacios rompen FFmpeg → usar Path().as_posix()
- [2026-03-08] Timeout ElevenLabs con textos >500 chars → dividir en chunks de 450
