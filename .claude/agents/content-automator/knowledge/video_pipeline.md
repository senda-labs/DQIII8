# Video Pipeline — Architecture and Flow

## Main Entrypoint

`scripts/professional_pipeline_v3.py`

Main function: `run_pipeline(topic, mode, channel, duration, language, dry_run)`
- No `publish` parameter — publishing is a separate step
- `dry_run=True` skips FFmpeg render, useful for TTS and subtitle testing

## Pipeline Modules

### 1. Script Generation
- Generates script by segments according to `mode` (viral_hook, finance, edu, etc.)
- Source: Groq llama-3.3-70b or OpenRouter depending on availability
- Output: list of dicts `{text, duration_s, segment_type}`

### 2. TTS — ElevenLabs / Edge Fallback
- Primary: `backend/services/elevenlabs_tts.py`
- Automatic fallback: Edge TTS if ElevenLabs fails or key is empty
- Mandatory chunking: texts > 450 chars → split before sending
- Output: .mp3 files per segment in /tmp/

### 3. Subtitle Generation
- Engine: `backend/services/netflix_subtitle_generator.py`
- Formats: ASS (primary) and SRT (fallback)
- Font palettes: `backend/graphics/typographic/palettes.py`
- FONT_BOLD_PREMIUM (LiberationSans-Bold) → only `viral_hook` and `finance` palettes

### 4. Video Composition / FFmpeg
- Combines TTS audio + background images/clips + ASS subtitles
- Critical path: `Path(...).resolve().as_posix()` for FFmpeg filters
- NEVER put quotes in filter paths `-vf`: `f"ass={path}"` ✓
- Zoompan: scale image to 1080×1920 before filter (avoids timeout >600s)

### 5. Output
- Final video: `tasks/results/` or directory configured in YAML
- Verify first 5s with `ffprobe` after any subtitle changes

## Configuration

- YAMLs in `config/` — NEVER edit directly, use config loader
- `.env` loads from `config/.env` with `override=True` → takes priority
- When rotating API key: sync BOTH the root `.env` and `config/.env`

## Available Modes

| mode | Description | Font palette |
|------|-------------|-------------|
| viral_hook | Viral social media hook | FONT_BOLD_PREMIUM |
| finance | Financial/investing content | FONT_BOLD_PREMIUM |
| edu | Educational / explainer | Standard |
| storytime | Narrative / story | Standard |

## System Dependencies

- FFmpeg installed in PATH
- LiberationSans-Bold: `apt-get install -y fonts-liberation && fc-cache -fv`
- ElevenLabs API key in config/.env and root .env

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| ASS filter not found | Quotes in FFmpeg path | Remove quotes from path |
| TTS timeout | Chunk > 500 chars | Split to <= 450 chars |
| zoompan slow | Full-res image in filter | Scale to 1080×1920 first |
| ElevenLabs 401 | Out-of-sync key | Sync both .env files |
| ModuleNotFoundError | Class renamed | grep "^class" before importing |
