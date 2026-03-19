# ElevenLabs — Best Practices

## Chunking Óptimo

Regla crítica: NUNCA enviar texto > 450 chars a la API.
- Textos entre 450–500 chars causan timeout intermitente
- Textos > 500 chars causan timeout garantizado
- Dividir siempre ANTES de llamar a la API, no como retry

Algoritmo de chunking:
```python
def chunk_text(text: str, max_chars: int = 450) -> list[str]:
    # Dividir por oraciones primero (respeta prosodia)
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

## Voces Disponibles (ElevenLabs v2)

Categorías principales:
- `Rachel` — narración femenina neutral, ideal para edu/finance
- `Adam` — narración masculina profesional
- `Bella` — femenina expresiva, viral_hook y storytime
- `Antoni` — masculino cálido, narración larga
- `Josh` — masculino profundo, finanzas y noticias

Parámetros de calidad:
- `model_id`: `eleven_multilingual_v2` para español (recomendado)
- `voice_settings.stability`: 0.5–0.7 (más alto = más consistente)
- `voice_settings.similarity_boost`: 0.75–0.85
- `output_format`: `mp3_44100_128` para calidad estándar

## Verificación de Clase y Método

Antes de integrar: siempre verificar nombres exactos.
```bash
grep -n "^class\|^    def " backend/services/elevenlabs_tts.py | head -20
```

Errores comunes de naming (lessons aprendidas):
- El cliente se inicializa con `ElevenLabs(api_key=...)` no `ElevenLabsClient`
- El método TTS puede ser `.generate()` o `.text_to_speech.convert()`
- Verificar siempre contra la versión instalada: `pip show elevenlabs`

## Fallback a Edge TTS

Activar fallback cuando:
- ElevenLabs key vacía o inválida (401)
- Créditos agotados (402)
- Timeout después de retry

```python
try:
    audio = elevenlabs_generate(text, voice_id)
except (ElevenLabsError, requests.Timeout):
    audio = edge_tts_generate(text, voice="es-ES-AlvaroNeural")
```

## Sincronización de API Keys

Keys en DOS lugares — deben estar sincronizadas:
1. `/root/dqiii8/.env` — configuración global DQIII8
2. `/root/content-automation-faceless/config/.env` — pipeline (override=True)

Si una key se rota y solo se actualiza en un lugar:
- config/.env tiene prioridad (override=True) → dqiii8/.env ignorado
- Pipeline usará key caducada silenciosamente hasta error 401

Procedimiento al rotar key:
```bash
# Actualizar ambos archivos
sed -i 's/ELEVENLABS_API_KEY=.*/ELEVENLABS_API_KEY=nueva_key/' /root/dqiii8/.env
sed -i 's/ELEVENLABS_API_KEY=.*/ELEVENLABS_API_KEY=nueva_key/' /root/content-automation-faceless/config/.env
# Verificar
grep ELEVENLABS /root/dqiii8/.env
grep ELEVENLABS /root/content-automation-faceless/config/.env
```

## Diagnóstico de Errores

| Error | Síntoma | Causa | Fix |
|-------|---------|-------|-----|
| 401 Unauthorized | TTS cae a Edge silenciosamente | Key caducada o vacía | Sincronizar ambos .env |
| 422 Unprocessable | Sin audio generado | Texto con chars especiales | Sanitizar texto antes de enviar |
| Timeout >30s | TTS muy lento | Chunk > 500 chars | Dividir texto a ≤ 450 |
| AttributeError | Método no encontrado | Versión API distinta | grep "^def" en el módulo |
