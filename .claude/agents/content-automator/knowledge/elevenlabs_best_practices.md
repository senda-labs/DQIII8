# ElevenLabs — Best Practices

## Optimal Chunking

Critical rule: NEVER send text > 450 chars to the API.
- Texts between 450–500 chars cause intermittent timeouts
- Texts > 500 chars cause guaranteed timeouts
- Always split BEFORE calling the API, not as a retry

Chunking algorithm:
```python
def chunk_text(text: str, max_chars: int = 450) -> list[str]:
    # Split by sentences first (preserves prosody)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) <= max_chars:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks
```

## Available Voices (ElevenLabs v2)

Main categories:
- `Rachel` — neutral female narration, ideal for edu/finance
- `Adam` — professional male narration
- `Bella` — expressive female, viral_hook and storytime
- `Antoni` — warm male, long narration
- `Josh` — deep male, finance and news

Quality parameters:
- `model_id`: `eleven_multilingual_v2` for non-English content (recommended)
- `voice_settings.stability`: 0.5–0.7 (higher = more consistent)
- `voice_settings.similarity_boost`: 0.75–0.85
- `output_format`: `mp3_44100_128` for standard quality

## Class and Method Verification

Before integrating: always verify exact names.
```bash
grep -n "^class\|^    def " backend/services/elevenlabs_tts.py | head -20
```

Common naming errors (learned lessons):
- Client initializes with `ElevenLabs(api_key=...)` not `ElevenLabsClient`
- TTS method may be `.generate()` or `.text_to_speech.convert()`
- Always verify against the installed version: `pip show elevenlabs`

## Fallback to Edge TTS

Activate fallback when:
- ElevenLabs key empty or invalid (401)
- Credits exhausted (402)
- Timeout after retry

```python
try:
    audio = elevenlabs_generate(text, voice_id)
except (ElevenLabsError, requests.Timeout):
    audio = edge_tts_generate(text, voice="en-US-GuyNeural")
```

## API Key Synchronization

Keys in TWO places — must stay in sync:
1. `$JARVIS_ROOT/.env` — global DQIII8 configuration
2. Pipeline config `.env` — pipeline (override=True)

If a key is rotated and only updated in one place:
- config/.env has priority (override=True) → root .env ignored
- Pipeline will silently use the expired key until 401 error

Rotation procedure:
```bash
# Update both files
sed -i 's/ELEVENLABS_API_KEY=.*/ELEVENLABS_API_KEY=new_key/' "$JARVIS_ROOT/.env"
sed -i 's/ELEVENLABS_API_KEY=.*/ELEVENLABS_API_KEY=new_key/' /path/to/pipeline/config/.env
# Verify
grep ELEVENLABS "$JARVIS_ROOT/.env"
grep ELEVENLABS /path/to/pipeline/config/.env
```

## Error Diagnosis

| Error | Symptom | Cause | Fix |
|-------|---------|-------|-----|
| 401 Unauthorized | TTS silently falls back to Edge | Expired or empty key | Sync both .env files |
| 422 Unprocessable | No audio generated | Text with special chars | Sanitize text before sending |
| Timeout >30s | TTS very slow | Chunk > 500 chars | Split text to ≤ 450 |
| AttributeError | Method not found | Different API version | grep "^def" in the module |
