# Fase C — Reporte Final para Gemini Pro

**Fecha:** 2026-03-15
**Pipeline:** content-automation-faceless
**Test:** V5 — Full pipeline + FFmpegComplexRenderer benchmark

---

## ✅ Entregables Completados

| # | Entregable | Estado | Notas |
|---|-----------|--------|-------|
| C0 | Audit de imports `ffmpeg_renderer` | ✅ | 0 imports activos pre-creación |
| C1 | MD5 cache en ImageService | ✅ | `hashlib.md5()`, determinístico entre sesiones |
| C2 | `ffmpeg_renderer.py` creado | ✅ | FFmpegComplexRenderer, SceneAsset, RenderJob |
| C3 | Test V5 pipeline completo | ✅ | Video 14.66MB, score 8.2/10 |
| — | Video enviado a Telegram | ✅ | MP4 enviado con caption de métricas |

---

## 📊 Test V5 — Resultados

**Tema:** "The horrific truth about plague doctors in 1347. They were not healers."
**Config:** `mode=viral_hook`, `duration=35`, `language=en`

| Métrica | Valor |
|---------|-------|
| Script viral score | 8.2/10 ⭐ |
| ElevenLabs TTS | ✅ (504 chars, George voice) |
| asyncio.TaskGroup (TTS + imgs) | ✅ paralelo |
| Imágenes | 5 × Unsplash (plague doctor) |
| Color grading | ✅ 5 imágenes |
| CompositeRenderer | 1002 frames, Ken Burns |
| Subtítulos | 30 líneas, hard-chunked (PARCHE 1) |
| Duración video | 33.4s |
| Resolución | 1080×1920 ✅ |
| Tamaño | 14.66MB |
| Renderer usado | CompositeRenderer (MoviePy) |

---

## ⚠️ CRÍTICO: FFmpegComplexRenderer — Zoompan Timeout

### Hallazgo
El benchmark del FFmpegComplexRenderer reveló que el filtro `zoompan` a 1080×1920 en este VPS es **impracticable para producción**:

| Benchmark | Clips | Frames zoompan | Timeout | Resultado |
|-----------|-------|----------------|---------|-----------|
| Intento 1 | 3 × 11.67s | 1050 frames | 300s | ❌ TimeoutExpired |
| Intento 2 | 3 × 4.0s | 360 frames | 300s | ❌ TimeoutExpired |

**Rate medida en VPS:** ~1.2 frames/segundo de zoompan a 1080×1920
**Rate necesaria para viabilidad:** ~20+ frames/segundo

### Causa Raíz
El filtro `zoompan` de FFmpeg es:
- CPU-only (sin aceleración GPU)
- Single-threaded (no escala con más CPUs)
- O(n) por resolución — 1080×1920 es ~6× más pesado que 720×1280

### Comparación con Estimación Gemini
| | Estimación Gemini | Realidad VPS |
|---|---|---|
| Tiempo render 12s video | ~15s | >300s (timeout) |
| Mejora vs MoviePy | -83% | MoviePy más rápido |
| RAM | ~400MB | ~380MB (correcto) |

### Fix Implementado (código)
- `MAX_ZOOMPAN_FRAMES = 125` — cap de animación
- Split-path para clips largos: zoompan (4.17s) + static hold (remainder)
- Timeout dinámico: `max(300, total_zoompan_s * 12 + 60)`
- `STATIC_HOLD_TEMPLATE` para hold a 1.10× zoom sin costo CPU de zoompan

### Recomendación para Gemini
Tres opciones ordenadas por viabilidad:

1. **Opción A — GPU VPS**: Migrar a VPS con GPU (CUDA). `zoompan` con NVENC/VAAPI: ~20fps expected. Cost: ~€15-30/mes adicional.

2. **Opción B — Ken Burns manual sin zoompan**: Usar `scale+overlay+setpts` para simular zoom sin el filtro zoompan. Implementar con ffmpeg `-vf "scale=1188:2112,crop=1080:1920,setpts=PTS*(1+0.0015*N/30)"` — más simple, más rápido (CPU paralelo).

3. **Opción C — MoviePy como producción**: Mantener CompositeRenderer (MoviePy) como path de producción. FFmpegComplexRenderer queda como opción futura para GPU. La mejora de calidad de Parches 1-3 ya justifica el sprint sin FFmpeg.

---

## ✅ Todos los Parches Gemini — Estado

| Parche | Archivo | Estado | Verificación |
|--------|---------|--------|-------------|
| 1 — Hard Chunking | `netflix_subtitle_generator.py` | ✅ | `_chunk_text_hormozi` → ['UNO DOS TRES', 'CUATRO CINCO SEIS', 'SIETE'] |
| 2 — Viral Hook | `script_service.py` | ✅ | `VIRAL HOOK RULES` in system prompt |
| 3a — Remove ffmpeg_composer | `renderer.py` | ✅ | grep 0 resultados en fast-path |
| 3b — Fix _sfx doble sufijo | `sound_design.py` | ✅ | `re.sub(r'(_with_music|_sfx)+$', '', stem)` |

---

## 📁 Archivos Modificados (Fase B + C)

| Archivo | Cambio | LOC |
|---------|--------|-----|
| `backend/services/image_service.py` | MD5 cache, Fal.ai subscribe_async | +60 |
| `backend/services/ffmpeg_renderer.py` | Nuevo — FFmpegComplexRenderer | +180 |
| `backend/services/elevenlabs_tts_service.py` | `generate_async()` | +8 |
| `scripts/pipeline/renderer.py` | TaskGroup paralelo, process_scene_parallel | +45 |
| `backend/services/netflix_subtitle_generator.py` | Hard chunking | +40 |
| `backend/services/script_service.py` | Viral hook rules | +7 |
| `backend/services/sound_design.py` | Fix _sfx doble sufijo | -3 |
| `.deprecated/` | 3 archivos dead code (542 LOC purgadas) | -542 |

---

## 🔜 Siguiente Pregunta para Gemini

> **Fase C — Zoompan Decision:**
> El VPS no puede ejecutar zoompan a 1080×1920 en tiempo útil.
> ¿Apruebas Opción B (Ken Burns manual sin zoompan) como path de producción?
> ¿O postponemos FFmpegComplexRenderer hasta migrar a GPU VPS?
> El video del Test V5 está en Telegram para revisión visual.

---

*Generado: 2026-03-15 | claude-sonnet-4-6*
