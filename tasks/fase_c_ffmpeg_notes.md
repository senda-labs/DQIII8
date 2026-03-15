# Fase C — Filtro FFmpeg zoompan validado por Gemini Pro

**Validado:** 2026-03-15
**Fuente:** Gemini Pro audit — Fase B authorization note

## Correcciones aplicadas al filtro original:
- zoom MAX **1.10** (no 1.5 — destruye resolución a 1080p)
- `s=1080x1920` forzado (evita bug temblor 1px en bordes del concat)
- `unsharp` después del zoom (compensa pérdida de nitidez del zoompan)
- `d=125` frames @ 30fps = 4.17s por imagen (compatible con MAX_CLIP_DURATION=2.5s si se ajusta d)

## Filtro validado:

```python
FFMPEG_ZOOMPAN = (
    "zoompan=z='min(zoom+0.0015,1.10)'"
    ":d=125"
    ":x='iw/2-(iw/zoom/2)'"
    ":y='ih/2-(ih/zoom/2)'"
    ":s=1080x1920"
    ",unsharp=5:5:0.8:3:3:0.4"
)
```

## Uso en Fase C (FFmpegComplexRenderer):

```bash
ffmpeg -loop 1 -t {duration} -i image.jpg \
  -vf "scale=1188:2112,crop=1080:1920,{FFMPEG_ZOOMPAN}" \
  -t {duration} -r 30 output_clip.mp4
```

## Notas de implementación Fase C:

### Estrategia recomendada (Gemini):
1. Fal.ai genera imágenes a 1080×1920 (portrait_16_9 preset)
2. Para evitar desenfoque en zoom 1.10x → generar a **1188×2112** si Fal.ai lo permite (10% margen)
   O aplicar `unsharp=5:5:0.8:3:3:0.4` post-zoompan (ya incluido en filtro)
3. Cada imagen → clip MP4 individual con zoompan
4. Concat de clips + audio + ASS en un solo pass final

### Rendimiento esperado en VPS (4 CPU / 8GB RAM):
- MoviePy Ken Burns: ~90s por video de 30s, ~3GB RAM
- FFmpeg zoompan: ~15s por video de 30s, <500MB RAM
- Reducción estimada: **-83% tiempo render, -83% RAM**

### codec flags para VPS:
```
-c:v libx264 -preset veryfast -crf 23 -threads 4
```
`veryfast` sobre `fast`: -40% tiempo encode, +5% tamaño (aceptable para VPS)

### Pipeline Fase C:
```
[Fal.ai imgs] → [zoompan per img] → [concat] → [ASS burn-in] → [audio mix] → MP4
```
vs Pipeline actual (Fase B):
```
[Stock imgs] → [MoviePy Ken Burns] → [concat] → [ASS burn-in] → [audio mix] → MP4
```

## Pendiente antes de Fase C:
- [ ] Recargar balance Fal.ai (agotado en test Fase B)
- [ ] Verificar que `portrait_16_9` produce exactamente 1080×1920 (o ajustar escala)
- [ ] Benchmark zoompan en VPS (4 CPUs): tiempo real para video 30s, 5 imágenes
- [ ] Autorización Gemini Pro post-Fase B
