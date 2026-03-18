# Video Pipeline — Arquitectura y Flujo

## Entrypoint Principal

`/root/content-automation-faceless/scripts/professional_pipeline_v3.py`

Función principal: `run_pipeline(topic, mode, channel, duration, language, dry_run)`
- Sin parámetro `publish` — la publicación es paso separado
- `dry_run=True` salta render FFmpeg, útil para test de TTS y subtítulos

## Módulos del Pipeline

### 1. Script Generation
- Genera guión por segmentos según `mode` (viral_hook, finance, edu, etc.)
- Fuente: Groq llama-3.3-70b o OpenRouter según disponibilidad
- Output: lista de dicts `{text, duration_s, segment_type}`

### 2. TTS — ElevenLabs / Edge Fallback
- Principal: `backend/services/elevenlabs_tts.py`
- Fallback automático: Edge TTS si ElevenLabs falla o está vacío
- Chunking obligatorio: textos > 450 chars → dividir antes de enviar
- Output: archivos .mp3 por segmento en /tmp/

### 3. Subtitle Generation
- Motor: `backend/services/netflix_subtitle_generator.py`
- Formatos: ASS (primario) y SRT (fallback)
- Paletas de fuente: `backend/graphics/typographic/palettes.py`
- FONT_BOLD_PREMIUM (LiberationSans-Bold) → solo paletas `viral_hook` y `finance`

### 4. Video Composition / FFmpeg
- Combina audio TTS + imágenes/clips de fondo + subtítulos ASS
- Ruta crítica: `Path(...).resolve().as_posix()` para filtros FFmpeg
- NUNCA poner comillas en paths de filtros `-vf`: `f"ass={path}"` ✓
- Zoompan: escalar imagen a 1080×1920 antes del filtro (evita timeout >600s)

### 5. Output
- Vídeo final: `tasks/results/` o directorio configurado en YAML
- Verificar primeros 5s con `ffprobe` tras cualquier cambio en subtítulos

## Configuración

- YAMLs en `config/` — NUNCA editar directamente, usar config loader
- `.env` carga desde `config/.env` con `override=True` → tiene prioridad
- Al rotar API key: sincronizar AMBOS `/root/jarvis/.env` y `config/.env`

## Modos Disponibles

| mode | Descripción | Paleta fuente |
|------|------------|--------------|
| viral_hook | Gancho viral redes sociales | FONT_BOLD_PREMIUM |
| finance | Contenido financiero/investing | FONT_BOLD_PREMIUM |
| edu | Educativo / explainer | Standard |
| storytime | Narrativa / historia | Standard |

## Dependencias de Sistema

- FFmpeg instalado en PATH
- LiberationSans-Bold: `apt-get install -y fonts-liberation && fc-cache -fv`
- ElevenLabs API key en config/.env y /root/jarvis/.env

## Errores Frecuentes

| Error | Causa | Fix |
|-------|-------|-----|
| ASS filter not found | Comillas en path FFmpeg | Eliminar comillas del path |
| TTS timeout | Chunk > 500 chars | Dividir a <= 450 chars |
| zoompan lento | Imagen full-res en filtro | Escalar a 1080×1920 antes |
| ElevenLabs 401 | Key desincronizada | Sincronizar ambos .env |
| ModuleNotFoundError | Clase renombrada | grep "^class" antes de importar |
