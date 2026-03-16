---
name: fal-ai-media
description: Use this skill when generating images or videos via fal.ai in the content-automation-faceless pipeline. Covers flux-general, negative prompts, reference images, and cost estimation.
origin: ECC/affaan-m (adaptado para content-automation-faceless — flux-general, Seedance, ElevenLabs)
status: APROBADA
---

# fal.ai Media Skill

## When to Activate

- Implementing or modifying `backend/services/visual_matcher.py`
- Changing image generation model in `scene_director.py`
- Adding video generation to the pipeline
- Debugging fal.ai API errors (timeout, quota, model not found)

## Image Generation

### flux-general (modelo activo — contenido viral)

```python
import fal_client

result = fal_client.subscribe(
    "fal-ai/flux-general",
    arguments={
        "prompt": scene.fal_prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "image_size": "portrait_4_3",         # 9:16 para Reels/TikTok → usar portrait_4_3
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "reference_image_url": scenes[0].image_url if scene.index > 0 else None,
        "reference_strength": 0.35,           # coherencia visual sin clonación
        "output_format": "jpeg",
        "num_images": 1,
        "enable_safety_checker": False,
    }
)
image_url = result["images"][0]["url"]
```

### NEGATIVE_PROMPT estándar (anti-artifacts)

```python
NEGATIVE_PROMPT = (
    "blurry faces, distorted anatomy, deformed hands, modern clothing, "
    "anachronistic items, smartphones, text overlays, watermarks, UI elements, "
    "cartoon style, painting artifacts, low resolution, AI glitch artifacts, "
    "multiple same person, clones, tiling patterns, repeated elements"
)
```

### Parámetros comunes

| Parámetro | Valor recomendado | Notas |
|-----------|------------------|-------|
| `image_size` | `"portrait_4_3"` | 1024×1365 — óptimo para Reels |
| `guidance_scale` | `3.5` | Menor = más creativo, mayor = más fiel al prompt |
| `num_inference_steps` | `28` | Balance calidad/velocidad |
| `reference_strength` | `0.35` | Solo para escenas 1-4 (coherencia de paleta) |
| `output_format` | `"jpeg"` | Más rápido que PNG para pipeline |

## Video Generation

### Seedance 1.0 Pro (image-to-video, ByteDance)

```python
result = fal_client.subscribe(
    "fal-ai/seedance-1-0-pro",
    arguments={
        "prompt": "camera slowly zooms out, gentle wind, cinematic",
        "image_url": scene.image_url,        # imagen generada en fase anterior
        "duration": "5s",
        "aspect_ratio": "9:16",
    }
)
video_url = result["video"]["url"]
```

### Kling Video v3 Pro (alta fidelidad)

```python
result = fal_client.subscribe(
    "fal-ai/kling-video/v1.6/pro/image-to-video",
    arguments={
        "prompt": "cinematic slow push, film grain, amber light",
        "image_url": scene.image_url,
        "duration": "5",                     # segundos como string
        "aspect_ratio": "9:16",
    }
)
```

## Estimación de costes

| Operación | Coste aprox. |
|-----------|-------------|
| flux-general imagen | ~$0.003-0.006 |
| Seedance 5s video | ~$0.05-0.10 |
| Kling 5s video | ~$0.10-0.20 |
| Pipeline completo (5 escenas, solo imágenes) | ~$0.02-0.04 |
| Pipeline completo (5 escenas, imagen+video) | ~$0.30-0.60 |

## Descargar y guardar imagen

```python
import httpx
from pathlib import Path

def download_image(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(url, timeout=60)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest
```

## Model Discovery

```python
# Listar modelos disponibles
result = fal_client.subscribe("fal-ai/any-llm", arguments={"model": "list"})
```

O buscar en https://fal.ai/models con filtro `image-to-image`, `text-to-image`.

## Tips JARVIS

1. **Escena 0 primero** — Generar escena 0 sola, obtener `image_url`, luego usar como `reference_image_url` para escenas 1-4.
2. **Paralelismo** — Escenas 1-4 pueden generarse en paralelo con `asyncio.gather()` una vez se tiene la URL de referencia.
3. **Reintentos** — fal.ai puede timeoutear. Máximo 2 reintentos, espera 5s entre intentos.
4. **Logging** — Guardar `image_url`, `image_path`, y `image_score` en `scene_scripts` tabla.
5. **FAL_KEY** — Cargar desde `/root/content-automation-faceless/config/.env` (prioridad) o `/root/jarvis/.env`.

## Errores comunes

| Error | Causa | Fix |
|-------|-------|-----|
| `model_not_found` | Model ID incorrecto | Verificar en fal.ai/models |
| `quota_exceeded` | Límite de API | Esperar o usar modelo alternativo |
| `invalid_reference_image` | URL expirada | Re-generar escena 0 antes de usarla |
| `timeout` | Red o modelo lento | Retry con backoff exponencial |

## Related

- `visual_matcher.py` — implementación del cliente fal.ai
- `scene_director.py` — generación de prompts (`_build_fal_prompts`)
- Plan arquitectónico: `tasks/gemini_reports/` — análisis de flux-general vs flux/dev
