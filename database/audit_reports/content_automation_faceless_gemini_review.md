# Evaluación Externa — content-automation-faceless
**Documento para revisión por Gemini Pro**
Fecha: 2026-03-14 | Auditor interno: JARVIS (Claude Sonnet 4.6)

---

## 1. Identidad del Proyecto

| Campo | Valor |
|---|---|
| Nombre | content-automation-faceless |
| Repositorio | github.com/ikermartiinsv-eng/content-automation-faceless |
| Rama principal | main |
| Total commits | 76 (todos en el último mes, arranque 2026-03-03) |
| Estado declarado | Día 10 / v4.0 — 96% funcional |
| Objetivo | Pipeline automatizado de vídeos faceless para YouTube Shorts, TikTok e Instagram Reels |
| Control | Bot de Telegram como panel de control |
| Stack | Python 3.11/3.12, FastAPI (no activo aún), SQLite, MoviePy, FFmpeg |

---

## 2. Estructura de Carpetas y Archivos

```
content-automation-faceless/             (2.3 GB total, venv incluido)
│
├── backend/                             # Núcleo del sistema
│   ├── __init__.py
│   │
│   ├── graphics/                        # Renderizado visual (~3070 líneas)
│   │   ├── base_renderer.py             # 51 líneas — interfaz abstracta
│   │   ├── content_plan_builder.py      # 92 líneas — construye ContentPlan desde Bible
│   │   ├── hf_background.py             # 411 líneas — generación fondos HuggingFace SDXL
│   │   ├── post_processing.py           # 202 líneas — vignette, tone_mapping, LUT
│   │   ├── renderer_selector.py         # 119 líneas — selecciona renderer por canal/modo
│   │   ├── scene_renderers.py           # 86 líneas — renderizadores de escena individuales
│   │   ├── transition_engine.py         # 146 líneas — 12-frame crossfade entre escenas
│   │   │
│   │   ├── procedural/                  # Renderer procedural (~1170 líneas)
│   │   │   ├── procedural_renderer.py   # 517 líneas — gradientes, partículas, geometría
│   │   │   └── composite_renderer.py    # 653 líneas — orquestador imagen+tipografía+efectos
│   │   │
│   │   ├── scene_intelligence/          # Clasificación semántica de escenas (~636 líneas)
│   │   │   ├── classifier.py            # 561 líneas — clasifica escena por tipo narrativo
│   │   │   └── descriptor.py            # 75 líneas — genera descripción visual de escena
│   │   │
│   │   └── typographic/                 # Renderer tipográfico (~872 líneas)
│   │       ├── palettes.py              # 130 líneas — paletas de color por canal
│   │       ├── typographic_renderer.py  # 62 líneas — router tipográfico
│   │       └── scenes/                  # Tipos de tarjetas visuales
│   │           ├── title_card.py        # 192 líneas
│   │           ├── body_card.py         # 127 líneas
│   │           ├── concept_card.py      # 264 líneas
│   │           ├── data_card.py         # 278 líneas
│   │           └── identity_card.py     # 211 líneas
│   │
│   ├── intelligence/                    # Capa de IA creativa (~1780 líneas)
│   │   ├── bible_generator.py           # 370 líneas — genera "Creative Bible" (master doc)
│   │   ├── bible_to_content_plan.py     # 102 líneas — Bible → ContentPlan estructurado
│   │   ├── memory_layer.py              # 230 líneas — SQLite memoria de canales y temas
│   │   ├── narrator_generator.py        # 339 líneas — narrador derivado del Bible por canal
│   │   ├── scene_evaluator.py           # 130 líneas — evalúa calidad de escena individual
│   │   ├── thumbnail_selector.py        # 89 líneas — selecciona frame climax para thumbnail
│   │   └── viral_reviewer.py            # 520 líneas — revisión viral por criterios de canal
│   │
│   ├── services/                        # Servicios del pipeline (~6546 líneas)
│   │   ├── asset_library.py             # 237 líneas — SQLite: assets, videos, temas (v2.0)
│   │   ├── color_grader.py              # 100 líneas — color grading cinematográfico
│   │   ├── content_modes.py             # 319 líneas — 14 modos narrativos definidos
│   │   ├── content_quality_gate.py      # 942 líneas — quality gate (legacy, fallback)
│   │   ├── elevenlabs_media_generator.py# 481 líneas — generación imágenes IA via ElevenLabs
│   │   ├── elevenlabs_tts_service.py    # 138 líneas — TTS ElevenLabs + Edge TTS fallback
│   │   ├── image_generator.py           # 219 líneas — generador imágenes AI (Leonardo/Fal)
│   │   ├── keyword_generator.py         # 131 líneas — keywords por modo narrativo
│   │   ├── media_scraper.py             # 714 líneas — scraper Openverse/MET/NASA (legacy)
│   │   ├── motion_engine.py             # 557 líneas — Ken Burns: zoom/pan cinematográfico
│   │   ├── music_generator.py           # 185 líneas — Pixabay Music tracks reales (v3.0)
│   │   ├── narrative_analyzer_cinematic.py # 121 líneas — estructura 5 actos cinematográficos
│   │   ├── netflix_subtitle_generator.py# 383 líneas — subtítulos ASS sin overlap (v6.0)
│   │   ├── publisher.py                 # 273 líneas — publisher legacy (compatibilidad)
│   │   ├── script_generator.py          # 333 líneas — generador de scripts via LLM
│   │   ├── script_quality_scorer.py     # 147 líneas — quality control, score ≥7/10
│   │   ├── smart_image_fetcher.py       # 455 líneas — fetcher legacy (fallback)
│   │   ├── trend_monitor.py             # 212 líneas — Google Trends + RSS + Reddit
│   │   ├── viral_scorer.py              # 152 líneas — scoring viral LLM multi-plataforma
│   │   ├── visual_generator.py          # 363 líneas — orquestador visual (imagen+video IA)
│   │   ├── voice_library_manager.py     # 84 líneas — mapping canal→voz ElevenLabs
│   │   │
│   │   ├── analytics/
│   │   │   └── performance_tracker.py   # YouTube Analytics API + retroalimentación
│   │   │
│   │   ├── content/
│   │   │   ├── thumbnail_generator.py   # PIL thumbnails estilos por modo
│   │   │   └── series_manager.py        # Series episódicas + CTAs automáticos
│   │   │
│   │   ├── image_pipeline/              # Pipeline de imágenes CLIP v2.0
│   │   │   ├── __init__.py              # Orquestador: fetch → CLIP rank → cache SQLite
│   │   │   ├── cache/__init__.py
│   │   │   ├── ranker/
│   │   │   │   ├── clip_scorer.py       # CLIP ViT-B/32 local, ~0.1s/imagen
│   │   │   │   └── llm_validator.py     # LLM solo para borderline (score 0.15–0.35)
│   │   │   └── sources/
│   │   │       ├── pixabay.py           # Pixabay API (100 req/min, vertical)
│   │   │       ├── wikimedia.py         # Wikimedia Commons (histórico)
│   │   │       ├── flickr.py            # Flickr CC (naturaleza, viajes)
│   │   │       └── nasa.py              # NASA Image Library + APOD
│   │   │
│   │   └── publishing/                  # Publishers reales v2.0
│   │       ├── __init__.py              # Orquestador multi-plataforma
│   │       ├── youtube.py               # OAuth2 + upload resumable + thumbnail
│   │       ├── instagram.py             # Graph API v18, container+publish
│   │       └── tiktok.py                # Content Posting API v2, chunks
│   │
│   └── utils/__init__.py
│
├── config/
│   ├── config_loader.py                 # Singleton ConfigLoader v3
│   ├── system_config.yaml               # Configuración sistema
│   ├── content_types.yaml               # Tipos de contenido y parámetros
│   └── voice_profiles.yaml              # Perfiles de voz ElevenLabs + mapping
│
├── scripts/
│   ├── professional_pipeline_v3.py      # 983 líneas — Pipeline principal 7 pasos
│   └── telegram_bot.py                  # 1198 líneas — Bot control panel PTB v20
│
├── docs/
│   ├── README.md                        # Documentación técnica principal
│   ├── APIS.md                          # Guía de APIs externas
│   ├── API_SETUP.md                     # Setup paso a paso
│   ├── INICIO-RAPIDO.md                 # Quickstart guide
│   ├── PLAN.md                          # Plan original 30 días
│   ├── PROGRESO.md                      # Tracking diario de progreso
│   └── TTS_OPTIONS.md                   # Comparativa opciones TTS
│
├── database/
│   └── video_memory.db                  # SQLite memoria de vídeos (runtime)
│
├── output/                              # Generado en runtime (gitignored)
│   ├── videos/          (20 vídeos, 2–19 MB c/u)
│   ├── audio/           (archivos .mp3 por vídeo)
│   ├── subtitles/       (archivos .ass)
│   ├── thumbnails/      (JPG optimizados YouTube)
│   ├── quality_reports/ (JSON por ejecución)
│   ├── images/          (imágenes descargadas)
│   ├── ai_generated/    (imágenes IA generadas)
│   ├── graded/          (frames post color grading)
│   ├── temp_kb/         (Ken Burns frames temp)
│   └── processed/       (vídeos post-procesados)
│
├── assets/                              # 165 MB runtime (gitignored)
│   ├── images/          (pixabay, openverse, nasa)
│   ├── downloads/       (imágenes raw)
│   └── bot.log          (log del bot)
│
├── tests/
│   └── __init__.py                      # Sin tests implementados
│
├── .gitignore
├── CHANGELOG.md                         # Historial completo de cambios
├── README.md                            # Estado actual + arquitectura
└── requirements.txt                     # 25 dependencias declaradas
```

**Totales de código fuente:**
| Módulo | Archivos .py | Líneas aprox |
|---|---|---|
| backend/graphics/ | 16 | ~3,070 |
| backend/intelligence/ | 7 | ~1,780 |
| backend/services/ | 28 | ~6,546 |
| scripts/ | 2 | ~2,181 |
| config/ | 1 | ~200 |
| **TOTAL** | **54** | **~13,777** |

---

## 3. Pipeline Principal — 7 Pasos

```
INPUT: tema (string) vía Telegram o CLI
    │
    ▼
[0] BibleGenerator (intelligence/)
    → CreativeBible: master doc con SceneBriefs, visual descriptions, narrator style
    │
    ▼
[1] ScriptQualityScorer
    → Script LLM (Groq llama-3.3-70b) + quality gate score ≥7/10
    → Máx 3 intentos de regeneración automática
    │
    ▼
[2] NarrativeAnalyzerCinematic
    → Estructura 5 actos: Hook / Rising Action / Climax / Falling Action / Resolution
    → Asigna duración por acto
    │
    ▼
[3] ImagePipeline (CLIP v2.0)
    → fetch: Pixabay + Wikimedia + Flickr + NASA → pool de candidatos
    → rank: CLIP ViT-B/32 local (0.1s/imagen) → score de relevancia
    → borderline (0.15–0.35): LLM validator
    → cache: SQLite asset_library
    │
    ▼
[4] ColorGrader (opcional)
    → Ajuste cinematográfico por modo narrativo
    → LUT blend 25% + vignette 0.20 + tone mapping
    │
    ▼
[5a] ElevenLabsTTSService
    → Voz primaria: ElevenLabs (4 perfiles: George/Alice/Liam/Sarah)
    → Fallback: Edge TTS (es-ES-ElviraNeural, en-US-ChristopherNeural...)
    │
[5b] MusicGenerator v3.0
    → Tracks reales Pixabay Music (libres de derechos, por género)
    → Fallback: síntesis procedural (scipy/numpy)
    │
    ▼
[6] MotionEngine (Ken Burns) + CompositeRenderer
    → Zoom/pan cinematográfico sobre imágenes
    → 12-frame crossfade entre escenas
    → Overlay tipográfico (lower thirds, title cards)
    → Post-processing: vignette + tone_mapping
    → Resolución: 1080×1920 (vertical Shorts/Reels)
    │
    ▼
[7a] NetflixSubtitleGenerator v6.0
    → Subtítulos ASS con anti-overlap garantizado
    → Estilo viral (fuente grande, color accent, sombra)
    │
[7b] ThumbnailGenerator
    → PIL thumbnail con frame climax (auto-seleccionado)
    → Estilos por modo narrativo
    │
    ▼
OUTPUT: .mp4 final (2–19 MB) + .jpg thumbnail + .ass subtítulos + quality_report.json
```

---

## 4. Modos Narrativos (14 definidos)

| Modo | Estilo | Música | Plataforma target |
|---|---|---|---|
| `historian` | Narrador épico documental | Epic orchestral | YouTube |
| `journalist` | Reportaje urgente | Epic | YouTube / Instagram |
| `novelist` | Narrativa literaria profunda | Emotional | YouTube |
| `viral_hook` | Hook impactante, ritmo rápido | Epic | TikTok / Instagram |
| `meme_reader` | Meme / humor casual | Funny | TikTok |
| `reddit_story` | Reddit thread narrado | Funny | TikTok / YouTube |
| `twitter_thread` | Thread viral condensado | Epic | Twitter / TikTok |
| `terror_thrill` | Terror / thriller psicológico | Dark ambient | YouTube / TikTok |
| `asmr_history` | ASMR histórico susurrado | Chill | YouTube |
| `philosopher` | Reflexión filosófica pausada | Emotional | YouTube |
| `scientist` | Divulgación científica clara | Neutral | YouTube |
| `storyteller` | Cuento narrativo | Emotional | YouTube / Instagram |
| `news_anchor` | Noticias presentadas | News | YouTube |
| `comedian` | Humor estructurado | Funny | TikTok |

---

## 5. Integraciones Externas

| Servicio | Uso | Tipo | Tier |
|---|---|---|---|
| Groq (llama-3.3-70b-versatile) | Script, Bible, ViralReview, calificación | LLM primario | Free |
| ElevenLabs | TTS PROD (4 voces) | Audio primario | $11/mes |
| Edge TTS (Microsoft) | TTS fallback | Audio secundario | Gratis |
| Pixabay API | Imágenes stock + música | Imagen/Audio | Gratis |
| Wikimedia Commons | Imágenes históricas | Imagen | Gratis |
| Flickr CC | Naturaleza/viajes CC | Imagen | Gratis |
| NASA Image Library | Espacio/ciencia | Imagen | Gratis |
| HuggingFace (SDXL) | Fondos AI generados | Imagen | Free tier |
| CLIP ViT-B/32 (local) | Scoring relevancia imágenes | ML local | Gratis |
| YouTube Data API v3 | Publicación + Analytics | Distribución | Gratis |
| Instagram Graph API v18 | Publicación Reels | Distribución | Gratis |
| TikTok Content Posting API | Publicación | Distribución | Gratis (requiere aprobación) |
| Telegram Bot API | Panel de control | UI | Gratis |
| Google Trends (pytrends) | Monitoring de tendencias | Research | Gratis |
| Reddit RSS | Monitoring tendencias | Research | Gratis |

---

## 6. Dependencias Python (requirements.txt)

```
# Core
groq>=0.9.0
python-telegram-bot>=20.0
requests>=2.31.0
python-dotenv>=1.0.0
PyYAML>=6.0

# Audio/Video
elevenlabs>=1.0.0
edge-tts>=6.1.9
openai-whisper>=20231117
moviepy>=1.0.3
ffmpeg-python>=0.2.0

# Image Processing
Pillow>=10.0.0
numpy>=1.24.0

# Audio Processing
scipy>=1.11.0
soundfile>=0.12.1
pydub>=0.25.1

# CLIP scoring (imagen)
sentence-transformers>=2.7.0

# Trends & Scraping
feedparser>=6.0.10
pytrends>=4.9.2

# YouTube Publisher
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
```

**Dependencias del sistema:** ffmpeg, libsndfile, libGL (para CLIP/OpenCV).

---

## 7. Rendimiento Observado (datos reales de quality_reports/)

### Vídeos generados hasta la fecha
| Tema | Duración | Tamaño final | Renderer | Imágenes |
|---|---|---|---|---|
| El impacto de la IA en la economía | 28.8s | 11.73 MB | CompositeRenderer | 5/5 |
| El impacto de la IA en la economía (v2) | 29.5s | 10.75 MB | CompositeRenderer | 5/5 |
| El impacto de la inteligencia artificial | 30.0s | 11.71 MB | CompositeRenderer | 5/5 |
| ChatGPT Traffic Hack | ~30s | 13 MB | CompositeRenderer | 5/5 |
| Kronosaurus | ~30s | 13 MB | CompositeRenderer | 5/5 |
| The Fall of the Roman Empire | ~30s | 19 MB | CompositeRenderer | 5/5 |
| Epstein Scandal | ~30s | 2.4 MB | CompositeRenderer | 5/5 |
| Ukraine Russia Conflict | ~30s | 5.3 MB | CompositeRenderer | 5/5 |

**Total vídeos generados:** ~20 (incluyendo versiones intermedias)
**Resolución:** 1080×1920 (vertical, Shorts/Reels)
**Warnings en quality_reports:** 0 en todas las ejecuciones recientes

### Tiempo de generación estimado (sin benchmarks formales)
| Paso | Estimación |
|---|---|
| Bible + Script + ViralReview (Groq) | ~15–30s |
| Image fetch + CLIP scoring (5 imágenes) | ~5–15s |
| TTS ElevenLabs | ~5–10s |
| Music download/fetch | ~2–5s |
| Video render (MoviePy Ken Burns) | ~60–180s |
| Subtítulos ASS | <1s |
| **Total estimado** | **~2–4 minutos por vídeo** |

### Uso de RAM/CPU (estimaciones de stack, sin benchmark en vivo)
| Componente | RAM estimada | Notas |
|---|---|---|
| CLIP ViT-B/32 (sentence-transformers) | ~500 MB | Cargado una vez, reutilizado |
| MoviePy render (1080×1920, 30s) | ~800 MB – 1.5 GB | Pico durante Ken Burns |
| Groq API calls | <50 MB | Red-bound, no RAM significativa |
| ElevenLabs TTS | <100 MB | Streaming descarga |
| HuggingFace SDXL (si activo) | ~4–6 GB VRAM / RAM | Solo si CIP_DRY_RUN=False |
| **Total sin SDXL** | **~1.5–2.5 GB RAM** | En VPS de 4 GB es ajustado |
| **Total con SDXL** | **~6–8 GB RAM/VRAM** | Requiere GPU o VPS potente |

**CPU:** El render MoviePy es CPU-bound. En un VPS de 2 cores, ~3–5 min/vídeo. Sin paralelización explícita actualmente.

---

## 8. Calidad Declarada vs Realidad Observada

| Componente | Calidad declarada | Estado real observado |
|---|---|---|
| Script LLM | 8/10 | Funcional, gate ≥7 automático, 3 reintentos |
| Audio ElevenLabs | 9.5/10 | Funcional, 4 voces verificadas |
| Audio Edge TTS (fallback) | 6/10 | Funcional, voz robótica |
| Subtítulos ASS | 9/10 | Sin overlap, estilo viral. Visibilidad en vídeo no verificada |
| Imágenes (CLIP pipeline) | 7–8/10 | 5/5 imágenes relevantes consistentemente |
| Música (Pixabay real) | 7.5/10 | Funcional en archivos con música |
| Ken Burns + compositing | 7.5/10 | CompositeRenderer activo, crossfade implementado |
| Color grading | 7/10 | Vignette + tone_mapping activos en quality_reports |
| Thumbnail auto | 7/10 | PIL funcional, frame climax auto-seleccionado |
| Publisher YouTube | Declarado ✅ | OAuth2 completo en código, no testeado en prod |
| Publisher Instagram | Declarado ✅ | Graph API v18 en código, no testeado en prod |
| Publisher TikTok | Declarado ✅ | API v2 en código, requiere aprobación TikTok |
| Telegram Bot | Declarado ✅ | PTB v20, comandos implementados |
| Analytics (YouTube) | Declarado ✅ | Código implementado, no activo en pipeline |

---

## 9. Problemas Conocidos y Deuda Técnica

### Criticos / Alta prioridad
1. **Subtítulos no verificados visualmente** — los .ass se generan pero no se ha confirmado que FFmpeg los queme correctamente en el vídeo final
2. **Publishers no testeados en producción** — YouTube/Instagram/TikTok tienen código completo pero sin end-to-end test real
3. **SDXL en modo DRY_RUN por defecto** — los fondos AI generados están desactivados (usa imágenes reales de Pixabay/NASA en su lugar). Variable de entorno `CIP_DRY_RUN`

### Media prioridad
4. **Sin tests** — `tests/__init__.py` vacío. Cero tests unitarios o de integración
5. **Módulos legacy sin deprecar formalmente** — `content_quality_gate.py` (942 líneas), `smart_image_fetcher.py` (455 líneas), `media_scraper.py` (714 líneas) permanecen como fallback pero no tienen contrato claro de cuándo se activan
6. **Paralelización ausente** — el pipeline es secuencial. Sin async en pasos independientes (fetch imágenes, TTS, música podrían ser concurrentes)
7. **RAM no gestionada** — CLIP model se carga cada vez o queda en memoria; no hay unload explícito

### Baja prioridad
8. **`config/env` expuso API keys en git** — corregido en auditoría 2026-03-14, pero el historial contiene las keys. Rotation necesaria
9. **Versiones intermedias duplicadas en output/** — 20 vídeos pero muchos son re-runs del mismo tema
10. **`docs/Grok Api KEY.docx`** trackeado en git — corregido en auditoría 2026-03-14
11. **`backend/data/voice_profiles.json`** duplicado obsoleto de `config/voice_profiles.yaml` — eliminado en auditoría
12. **Sin healthcheck ni monitoring** — el bot corre sin watchdog, sin alertas de fallo

---

## 10. Arquitectura — Diagrama de Dependencias

```
telegram_bot.py (1198 líneas)
    │  UI de control: /video /trends /stats /series
    │
    └──► professional_pipeline_v3.py (983 líneas)
              │
              ├─[0]─► intelligence/bible_generator.py
              │         └─► intelligence/narrator_generator.py
              │         └─► intelligence/viral_reviewer.py
              │
              ├─[1]─► services/script_quality_scorer.py
              │         └─► services/script_generator.py (Groq API)
              │
              ├─[2]─► services/narrative_analyzer_cinematic.py
              │
              ├─[3]─► services/image_pipeline/__init__.py
              │         ├─► sources/pixabay.py
              │         ├─► sources/wikimedia.py
              │         ├─► sources/flickr.py
              │         ├─► sources/nasa.py
              │         ├─► ranker/clip_scorer.py (CLIP local)
              │         └─► ranker/llm_validator.py (Groq borderline)
              │
              ├─[4]─► services/color_grader.py (opcional)
              │
              ├─[5a]─► services/elevenlabs_tts_service.py
              │          └─► ElevenLabs API / Edge TTS fallback
              │
              ├─[5b]─► services/music_generator.py
              │          └─► Pixabay Music API / síntesis procedural
              │
              ├─[6]─► services/motion_engine.py (Ken Burns)
              │         └─► graphics/composite_renderer.py
              │               ├─► graphics/hf_background.py (SDXL, DRY_RUN default)
              │               ├─► graphics/typographic/ (title/body/concept cards)
              │               ├─► graphics/post_processing.py
              │               └─► graphics/transition_engine.py
              │
              ├─[7a]─► services/netflix_subtitle_generator.py
              │
              ├─[7b]─► services/content/thumbnail_generator.py
              │          └─► intelligence/thumbnail_selector.py
              │
              └─[fin]─► services/asset_library.py (SQLite registro)
                         services/publishing/ (YouTube/Instagram/TikTok)
                         intelligence/memory_layer.py (aprendizaje)
```

---

## 11. Disco — Distribución del Espacio

| Directorio | Tamaño | Notas |
|---|---|---|
| `venv/` | 1.7 GB | Entorno virtual Python completo |
| `output/` | 445 MB | 20 vídeos + audio + imágenes + subtítulos |
| `assets/` | 165 MB | Imágenes descargadas (Pixabay, NASA, Reddit...) |
| Código fuente | ~1.5 MB | 54 ficheros .py, ~13.7k líneas |
| **Total proyecto** | **2.3 GB** | |

---

## 12. Historial de Desarrollo (76 commits en 11 días)

| Día | Hitos clave |
|---|---|
| 1–3 (03-03/05) | Estructura base, APIs config, primeros scripts |
| 4–6 (03-06/08) | Music v2, SmartImageFetcher, Config v3, primer vídeo completo |
| 7–8 (03-09/10) | Auditoría interna, CLIP pipeline, publishers reales |
| 9–10 (03-11/13) | BibleGenerator, NarratorGenerator, ViralReviewer v2, VoiceLibraryManager |
|   | HF parallel prefetch, auto-thumbnail from climax, 12-frame crossfade |
|   | Narrative-aware color grading, lower third text, LUT blend |

---

## 13. Preguntas Abiertas para Evaluación Externa (Gemini Pro)

1. **Arquitectura**: ¿El patrón de pipeline secuencial es adecuado para escalar a 10+ vídeos/día? ¿Qué cambiaría?
2. **Calidad de vídeo**: Los vídeos generados (2–19 MB, 30s, 1080×1920) ¿están dentro del rango competitivo para YouTube Shorts/TikTok?
3. **Deuda técnica**: Con 0 tests y 3 módulos legacy no deprecados formalmente, ¿cuál es el riesgo real de regresión?
4. **RAM**: ¿Es viable en un VPS de 4 GB RAM sin GPU? ¿Con SDXL activo?
5. **Publishers**: ¿El approach OAuth2 para YouTube + Graph API para Instagram es el correcto en 2026? ¿Qué ha cambiado?
6. **CLIP scoring local vs. LLM**: ¿Es CLIP ViT-B/32 suficientemente preciso para relevancia temática de imágenes stock?
7. **Monetización**: Con este pipeline, ¿cuántos canales se podrían gestionar en paralelo en un VPS de 8 GB?
8. **Seguridad**: Las API keys estuvieron en historial git. ¿Qué otros vectores de ataque presenta la arquitectura actual?
9. **Módulos innecesarios**: ¿Qué módulos eliminarías por bajo ROI (lines-of-code vs. valor real)?
10. **Camino a producción**: ¿Qué falta para que este sistema sea confiable 24/7 en VPS?
