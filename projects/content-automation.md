---
title: content-automation-faceless
tags: [project, active]
status: active
last_updated: 2026-03-12
agents: [content-automator, python-specialist, code-reviewer, shannon]
model: api
---
# content-automation-faceless — Estado del Proyecto

**Ruta:** `/root/content-automation-faceless/`
**Ultima actualizacion:** 2026-03-11
**Progreso declarado:** ~96% (Dia 10, README v4.0)
**Stack:** Python + MoviePy/FFmpeg + Groq (llama-3.3-70b) + ElevenLabs + SQLite + Telegram Bot PTB v20

---

## Agentes asignados
- Principal: content-automator
- Codigo: python-specialist
- Review: code-reviewer

## Modelo preferido
Claude API (video pipeline, TTS, publicacion multi-plataforma)

---

## Modulos existentes

### Entry points
| Archivo | Estado |
|---|---|
| `scripts/professional_pipeline_v3.py` | Funcional — pipeline 7 pasos |
| `scripts/telegram_bot.py` | Funcional — panel de control Telegram |

### Core services (`backend/services/`)
| Modulo | Version | Estado |
|---|---|---|
| `script_quality_scorer.py` | — | OK — quality control, 14 modos, score >=7/3 intentos |
| `narrative_analyzer_cinematic.py` | — | OK — estructura 5 actos cinematograficos |
| `elevenlabs_tts_service.py` | — | OK — ElevenLabs PROD + Edge TTS fallback |
| `music_generator.py` | v3.0 | OK — tracks reales Pixabay + fallback procedural |
| `netflix_subtitle_generator.py` | v6.0 | Generacion ASS OK — **incrustacion en video ROTA** |
| `asset_library.py` | v2.0 | OK — SQLite con migracion automatica |
| `color_grader.py` | — | OK — color grading cinematografico |
| `keyword_generator.py` | — | OK |
| `content_modes.py` | — | OK — 14 modos narrativos definidos |
| `script_generator.py` | — | Presente |
| `motion_engine.py` | — | Presente |
| `trend_monitor.py` | v1.0 | OK — Google Trends + RSS + Reddit |
| `viral_scorer.py` | v1.0 | OK — LLM scoring multi-plataforma |
| `elevenlabs_media_generator.py` | — | Presente — generacion imagenes IA |
| `image_generator.py` | — | Presente |
| `media_scraper.py` | — | Legacy — Openverse + MET + NASA |
| `smart_image_fetcher.py` | — | Legacy/fallback — Unsplash + Giphy + Pexels |
| `content_quality_gate.py` | — | Legacy/fallback |
| `publisher.py` | — | Legacy — compatibilidad |

### Image pipeline (`backend/services/image_pipeline/`) — v2.0
| Modulo | Estado |
|---|---|
| `__init__.py` | Orquestador CLIP + LLM borderline |
| `sources/pixabay.py` | OK — 100 req/min |
| `sources/wikimedia.py` | OK — historico |
| `sources/flickr.py` | OK — naturaleza/viajes CC |
| `sources/nasa.py` | OK — NASA APOD espacio |
| `ranker/clip_scorer.py` | OK — CLIP ViT-B/32 local, 0.1s/imagen |
| `ranker/llm_validator.py` | OK — LLM solo para casos borderline |

### Publishing (`backend/services/publishing/`) — v2.0
| Modulo | Estado |
|---|---|
| `youtube.py` | Declarado OK — OAuth2 + upload resumable + thumbnail |
| `instagram.py` | Declarado OK — Graph API v18 |
| `tiktok.py` | Declarado OK — Content Posting API v2 |

### Otros servicios
| Modulo | Estado |
|---|---|
| `content/thumbnail_generator.py` | v1.0 — PIL thumbnails por modo |
| `content/series_manager.py` | v1.0 — series episodicas + CTAs |
| `analytics/performance_tracker.py` | v1.0 — YouTube Analytics |
| `config/config_loader.py` | v3 Singleton — todas las keys |

---

## Calidad por componente

| Componente | Score | Notas |
|---|---|---|
| Script generation | 8/10 | Quality control automatico |
| Audio PROD (ElevenLabs) | 9.5/10 | Voces: George/Sarah/Liam/Alice |
| Audio TEST (Edge TTS) | 6/10 | Funcional pero robotico |
| Subtitulos | 9/10 generacion / **0 visibilidad** | ASS se genera, no aparece en video |
| Imagenes TEST | 6/10 | Unsplash devuelve fotos modernas para temas historicos |
| Imagenes PROD | 7/10 | Leonardo AI, aceptable |
| Musica | 7.5/10 | 5 generos, mezcla correcta |
| Ken Burns | 7.5/10 | Zoom 15%, 4 efectos |
| Color grading | 7/10 | Cinematografico automatico |

---

## Bugs conocidos

### Criticos
1. **Subtitulos no visibles en video final** — El archivo ASS v6.0 se genera sin overlap, pero FFmpeg no los incrusta visualmente. Causa probable: filtro `-vf ass=` mal aplicado o path incorrecto en `professional_pipeline_v3.py` paso 7.

### Importantes
2. **Imagenes historicas** — Unsplash/Pexels retornan fotos modernas para queries historicas. Solucion pendiente: frames de peliculas (300, Troy, Gladiator) o Midjourney.
3. **Edge TTS** — Calidad muy inferior a ElevenLabs en modo TEST.

---

## Fases pendientes

### Fase A — Calidad Visual (PROXIMA)
- [ ] Fix subtitulos: debuggear incrustacion FFmpeg en `professional_pipeline_v3.py` paso 7
- [ ] Imagenes cinematograficas: frames de peliculas o Midjourney API
- [ ] Evaluar ElevenLabs Image/Video API
- [ ] Evaluar Midjourney API

### Pre-publicacion (OBLIGATORIO antes de cada release)
- [ ] Ejecutar `/shannon` sobre `/root/content-automation-faceless/` antes de cada release
- [ ] Verificar Score seguridad >= 8/10 y Criticos = 0 antes de publicar
- [ ] Si CRITICO > 0 → BLOQUEAR publicacion hasta resolver

### Fase B — Distribucion
- [ ] Telegram Bot interfaz completa
- [ ] Auto-publicacion YouTube Shorts (OAuth2 ya configurado)
- [ ] Auto-publicacion TikTok (pendiente aprobacion API)
- [ ] Auto-publicacion Instagram Reels

### Fase C — Escalabilidad
- [ ] Colas Celery + Redis
- [ ] Deploy VPS 24/7
- [ ] Multiples cuentas/nichos
- [ ] Analytics y optimizacion automatica

---

## Proximo paso concreto

**Fix subtitulos visibles en video final.**

Archivo: `scripts/professional_pipeline_v3.py`, paso 7 (llamada FFmpeg).
Verificar: filtro `-vf ass=archivo.ass` o `-vf subtitles=archivo.ass`, que el path sea absoluto en runtime, y que el codec de video no ignore el filtro de subtitulos.
Modulo implicado: `backend/services/netflix_subtitle_generator.py` (generacion OK) + pipeline (incrustacion rota).

---

## Canales YouTube
- Echoes of the Past
- Primordial Economics
- Tao & Thought
- Football Chronicles
- Sapiens Origins

## APIs configuradas
- Groq (LLM gratis)
- ElevenLabs (Creator $11/mes)
- Pixabay (imagenes + musica, gratis)
- Flickr CC, NASA APOD (gratis)
- Telegram Bot (@AsistentAutomatorbot)
- YouTube Data API v3 + OAuth2
- Instagram Business API (@damnedpast)
- TikTok Content Posting API (pendiente aprobacion)

## Lecciones especificas
- [2026-03-09] Rutas Windows con espacios rompen FFmpeg — usar Path().as_posix()
- [2026-03-08] Timeout ElevenLabs con textos >500 chars — dividir en chunks de 450
