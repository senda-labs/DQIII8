---
name: fal-ai-media
description: Use this skill when generating images or videos via fal.ai in the content pipeline. Covers flux-general, negative prompts, reference images, and cost estimation.
origin: ECC/affaan-m (adapted for media pipeline — flux-general, Seedance, ElevenLabs)
status: APROBADA
---

# fal.ai Media Skill

## When to Activate

- Implementing or modifying `backend/services/visual_matcher.py`
- Changing image generation model in `scene_director.py`
- Adding video generation to the pipeline
- Debugging fal.ai API errors (timeout, quota, model not found)

## Image Generation

### flux-general (active model — viral content)

```python
import fal_client

result = fal_client.subscribe(
    "fal-ai/flux-general",
    arguments={
        "prompt": scene.fal_prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "image_size": "portrait_4_3",         # 9:16 for Reels/TikTok → use portrait_4_3
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "reference_image_url": scenes[0].image_url if scene.index > 0 else None,
        "reference_strength": 0.35,           # visual coherence without cloning
        "output_format": "jpeg",
        "num_images": 1,
        "enable_safety_checker": False,
    }
)
image_url = result["images"][0]["url"]
```

### Standard NEGATIVE_PROMPT (anti-artifacts)

```python
NEGATIVE_PROMPT = (
    "blurry faces, distorted anatomy, deformed hands, modern clothing, "
    "anachronistic items, smartphones, text overlays, watermarks, UI elements, "
    "cartoon style, painting artifacts, low resolution, AI glitch artifacts, "
    "multiple same person, clones, tiling patterns, repeated elements"
)
```

### Common parameters

| Parameter | Recommended value | Notes |
|-----------|------------------|-------|
| `image_size` | `"portrait_4_3"` | 1024×1365 — optimal for Reels |
| `guidance_scale` | `3.5` | Lower = more creative, higher = closer to prompt |
| `num_inference_steps` | `28` | Quality/speed balance |
| `reference_strength` | `0.35` | Only for scenes 1-4 (palette coherence) |
| `output_format` | `"jpeg"` | Faster than PNG for pipeline |

## Video Generation

### Seedance 1.0 Pro (image-to-video, ByteDance)

```python
result = fal_client.subscribe(
    "fal-ai/seedance-1-0-pro",
    arguments={
        "prompt": "camera slowly zooms out, gentle wind, cinematic",
        "image_url": scene.image_url,        # image generated in prior phase
        "duration": "5s",
        "aspect_ratio": "9:16",
    }
)
video_url = result["video"]["url"]
```

### Kling Video v3 Pro (high fidelity)

```python
result = fal_client.subscribe(
    "fal-ai/kling-video/v1.6/pro/image-to-video",
    arguments={
        "prompt": "cinematic slow push, film grain, amber light",
        "image_url": scene.image_url,
        "duration": "5",                     # seconds as string
        "aspect_ratio": "9:16",
    }
)
```

## Cost estimation

| Operation | Approx. cost |
|-----------|-------------|
| flux-general image | ~$0.003-0.006 |
| Seedance 5s video | ~$0.05-0.10 |
| Kling 5s video | ~$0.10-0.20 |
| Full pipeline (5 scenes, images only) | ~$0.02-0.04 |
| Full pipeline (5 scenes, image+video) | ~$0.30-0.60 |

## Download and save image

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
# List available models
result = fal_client.subscribe("fal-ai/any-llm", arguments={"model": "list"})
```

Or search at https://fal.ai/models with filter `image-to-image`, `text-to-image`.

## DQIII8 Tips

1. **Scene 0 first** — Generate scene 0 alone, get `image_url`, then use as `reference_image_url` for scenes 1-4.
2. **Parallelism** — Scenes 1-4 can be generated in parallel with `asyncio.gather()` once the reference URL is available.
3. **Retries** — fal.ai can timeout. Maximum 2 retries, wait 5s between attempts.
4. **Logging** — Save `image_url`, `image_path`, and `image_score` in `scene_scripts` table.
5. **FAL_KEY** — Load from pipeline `config/.env` (priority) or `$JARVIS_ROOT/.env`.

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `model_not_found` | Incorrect model ID | Check at fal.ai/models |
| `quota_exceeded` | API limit reached | Wait or use alternative model |
| `invalid_reference_image` | Expired URL | Re-generate scene 0 before using it |
| `timeout` | Network or slow model | Retry with exponential backoff |

## Related

- `visual_matcher.py` — fal.ai client implementation
- `scene_director.py` — prompt generation (`_build_fal_prompts`)
- Architecture plans: `tasks/gemini_reports/` — flux-general vs flux/dev analysis
