# MoneyPrinterTurbo — OSS Research (Task C2)

Date: 2026-06-10
Source: https://github.com/harry0703/MoneyPrinterTurbo (cloned depth-1 → `/tmp/oss-research/mpt`)
Integration target: `my-projects/content-automation/` (CIP v2 faceless-video pipeline)
**Verdict: ADAPT** — lift two components, do not integrate wholesale. See §6.

---

## 1. What MoneyPrinterTurbo (MPT) Is

FastAPI + Streamlit faceless-video generator. Given a `video_subject`, it writes a script
with an LLM, narrates it with TTS, downloads matching **stock B-roll** from Pexels/Pixabay/Coverr,
burns subtitles, and renders a vertical/landscape short with MoviePy + FFmpeg.

Crucial architectural fact: **MPT does not generate visuals — it sources stock footage by
keyword.** This is the opposite of content-automation, which generates visuals with SDXL/Flux.
That single difference drives the whole verdict (§6).

Two processes (see `docker-compose.yml`):
- **api** — `python3 main.py` → `uvicorn app.asgi:app` on `127.0.0.1:8080` (REST)
- **webui** — Streamlit on `127.0.0.1:8501` (human operator UI)

Both mount the repo root as a shared volume; **all config lives in `config.toml`** inside that
volume — there is no env-var config path by default (relevant for the Docker snippet, §4).

---

## 2. Pipeline Map (script → TTS → assets → subtitles → render)

Source of truth: `app/services/task.py::start(task_id, params, stop_at="video")`.
A `stop_at` gate lets callers stop after any stage — this is the most reusable idea in the repo.

| # | Stage | Function | Engine / provider | `stop_at` gate |
|---|-------|----------|-------------------|----------------|
| 1 | Script | `llm.generate_script` | ~22 LLM providers (§5) | `script` |
| 2 | Terms (search keywords) | `llm.generate_terms` | same LLM | `terms` |
| 3 | Audio / TTS | `voice.tts` | edge-tts (default, free), azure v2, siliconflow, gemini, mimo | `audio` |
| 4 | Subtitles | `task.generate_subtitle` | `edge` (from TTS word boundaries) or `whisper` (faster-whisper, with fallback) | `subtitle` |
| 5 | Materials (assets) | `material.download_videos` | **stock download** Pexels / Pixabay / Coverr (or `local`) | `materials` |
| 6 | Render | `video.combine_videos` → `video.generate_video` | MoviePy + FFmpeg (libx264 default, optional hw encoders) | `video` (default) |
| 7 | Cross-post (opt) | `upload_post.cross_post_video` | upload-post.com → TikTok / Instagram | — |

Notes:
- Stage 5 is keyword stock retrieval, **not** generation. `video_source="local"` lets you feed
  your own clips and skip download — this is the only seam where content-automation's AI visuals
  could plug in.
- Subtitles come "free" from edge-tts word boundaries (no alignment pass); whisper is the fallback.
  content-automation already does word-level alignment, which is finer-grained.
- State is tracked via `app/services/state.py` (in-memory or Redis, §3).

---

## 3. API Surface (FastAPI, port 8080)

Router: `app/router.py` → `app/controllers/v1/video.py` + `llm.py`. All responses wrap
`{status, message, data}` (`BaseResponse`).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/videos` | Create full video task → `{task_id}` |
| POST | `/subtitle` | Run pipeline `stop_at="subtitle"` |
| POST | `/audio` | Run pipeline `stop_at="audio"` |
| GET | `/tasks` | List tasks |
| GET | `/tasks/{task_id}` | Query state/progress/result URLs |
| DELETE | `/tasks/{task_id}` | Delete task + artifacts |
| GET | `/musics` | List BGM |
| POST | `/musics` | Upload BGM |
| GET | `/video_materials` | List local materials |
| POST | `/video_materials` | Upload local material |
| GET | `/stream/{file_path:path}` | Stream output |
| GET | `/download/{file_path:path}` | Download output |

Task creation is async: `task_manager.add_task(task.start, task_id, params, stop_at)`.
Concurrency: `max_concurrent_tasks=5`, `max_queued_tasks=100` (429 when full).

### API contract — `POST /videos` body (`TaskVideoRequest` = `VideoParams`, `app/models/schema.py`)

Required: `video_subject: str`. Everything else defaults:

```jsonc
{
  "video_subject": "string (required)",
  "video_script": "",                 // if set, skips stage-1 LLM
  "video_terms": null,                // str|list; if set, skips stage-2 LLM
  "video_aspect": "9:16",             // 16:9 | 9:16 | 1:1
  "video_concat_mode": "random",      // random | sequential
  "video_transition_mode": null,      // None|Shuffle|FadeIn|FadeOut|SlideIn|SlideOut
  "video_clip_duration": 5,
  "video_count": 1,
  "video_source": "pexels",           // pexels | pixabay | local
  "video_materials": null,            // [{provider,url,duration}] when source=local
  "custom_audio_file": null,          // bypass TTS; disables subtitles
  "video_language": "",               // auto-detect
  "voice_name": "",                   // e.g. zh-CN-XiaoxiaoNeural-Female, or siliconflow:/mimo:/gemini: prefixed
  "voice_volume": 1.0, "voice_rate": 1.0,
  "bgm_type": "random", "bgm_file": "", "bgm_volume": 0.2,
  "subtitle_enabled": true,
  "subtitle_position": "bottom",      // top|bottom|center|custom
  "custom_position": 70.0,
  "font_name": "STHeitiMedium.ttc",
  "text_fore_color": "#FFFFFF", "text_background_color": true,
  "font_size": 60, "stroke_color": "#000000", "stroke_width": 1.5,
  "n_threads": 2,
  "paragraph_number": 1,              // 1..10
  "video_script_prompt": "",          // max 2000
  "custom_system_prompt": ""          // max 8000
}
```

Response: `{ "status": 200, "message": "success", "data": { "task_id": "<uuid>" } }`.
Poll `GET /tasks/{task_id}` → `data.{state, progress, videos[], combined_videos[]}`.

---

## 4. Docker Service Snippet for DQIII8 (env passthrough, NO hardcoded keys)

MPT's own `docker-compose.yml` mounts the repo and reads `config.toml` — there is **no
secret-via-env path** and it `restart: always`. For DQIII8 we keep MPT's API container but
(a) bind only to loopback, (b) inject secrets via env passthrough from the host `.env` (never
written into the image or compose file), and (c) seed `config.toml` from env at boot rather than
baking keys into the mounted file.

```yaml
# docker-compose snippet for DQIII8 — secrets come ONLY from the host environment / .env.
# No API key is ever written literally here. Values resolve from the shell / .env at `up` time.
services:
  mpt-api:
    image: moneyprinterturbo:local           # build locally; do NOT pull an image with baked config
    container_name: dqiii8-mpt-api
    working_dir: /MoneyPrinterTurbo
    command: ["python3", "main.py"]
    ports:
      - "127.0.0.1:8080:8080"                 # loopback only — never expose publicly
    environment:
      # Passthrough ONLY. ${VAR} reads the host env / .env; nothing is hardcoded.
      PEXELS_API_KEY: ${PEXELS_API_KEY:-}
      PIXABAY_API_KEY: ${PIXABAY_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      GROQ_API_KEY: ${GROQ_API_KEY:-}
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-}
      UPLOAD_POST_API_KEY: ${UPLOAD_POST_API_KEY:-}
      # DQIII8 invariant: Anthropic key MUST be empty in subprocess env (OAuth path).
      ANTHROPIC_API_KEY: ""
    env_file:
      - .env                                  # gitignored; supplies the ${VAR} values above
    volumes:
      - ./storage:/MoneyPrinterTurbo/storage  # outputs only — NOT the whole repo
      - ./config.toml:/MoneyPrinterTurbo/config.toml:ro
    restart: unless-stopped
```

Caveat: MPT reads keys from `config.toml`, not env, for most providers (only LiteLLM reads env
natively). So a tiny entrypoint shim must render `config.toml` from the env vars at boot
(`envsubst < config.toml.tpl > config.toml`). That keeps **zero secrets** in the repo/image while
still feeding MPT's TOML loader. Tier-C/B alignment: point `llm_provider="ollama"` (local, $0) or
`groq` ($0) — never default to `openai` in DQIII8.

---

## 5. Config & Provider Model (`config.example.toml`)

TOML, sectioned `[app] [whisper] [proxy] [azure] [siliconflow] [ui]`. Highlights:

- **LLM providers (~22)**: openai, aihubmix, moonshot, azure, qwen, deepseek, gemini, grok, groq,
  ollama, g4f (disabled), oneapi, cloudflare, minimax, mimo, ernie, modelscope, pollinations,
  **litellm** (100+ via gateway, reads keys from env). DQIII8 fit: ollama (Tier C $0) / groq (Tier B $0).
- **TTS engines**: edge-tts (default, **no key, free**), azure speech (`[azure] speech_key`),
  siliconflow, gemini, mimo. Voice routing by name prefix (`siliconflow:` / `mimo:` / `gemini:`).
- **Subtitle**: `subtitle_provider = "edge" | "whisper"` (`[whisper] model_size="large-v3"`, CPU int8).
- **Stock sources**: `pexels_api_keys=[]`, `pixabay_api_keys=[]`, `coverr_api_keys=[]` (multi-key
  rotation for rate limits), `tls_verify=true`.
- **State**: `enable_redis=false` (in-memory default), `max_concurrent_tasks=5`, `max_queued_tasks=100`.
- **Cross-post**: `[ui] upload_post_enabled`, `upload_post_api_key`, `upload_post_platforms=["tiktok","instagram"]`.
- All keys ship empty (`""` / `[]`) — no secrets in repo. Good hygiene; matches DQIII8 rules.

---

## 6. Integration Plan vs content-automation — Verdict: **ADAPT**

### Why not INTEGRATE (wholesale)
content-automation (CIP v2) is **architecturally more advanced** than MPT in the stage that
matters most: visuals. MPT downloads keyword-matched **stock B-roll**; content-automation
**generates** bespoke visuals (SDXL/Flux) tied to a creative bible. Running MPT end-to-end would
be a downgrade for the existing 5 channels. MPT's LLM, TTS, subtitle, and compose stages all have
direct, already-working counterparts in content-automation (`bible/narrator_generator`,
`tts_engine` (ElevenLabs), `subtitle_generator` (word-level), `composer` (FFmpeg)).

### Why not DISCARD
Two MPT components are genuinely additive and content-automation lacks them today:

1. **Stock-footage sourcing module** (`app/services/material.py::download_videos`,
   Pexels/Pixabay/Coverr with multi-key rotation + aspect/duration-aware clipping).
   content-automation has *no* stock track — it only generates. For channels like
   `football_chronicles` or `sapiens_origins`, real B-roll often beats SDXL. This is the highest-value lift.
2. **Cross-posting** (`app/services/upload_post.py` → TikTok/Instagram via upload-post.com).
   content-automation's Next Step #3 is "Automate upload via YouTube API"; MPT covers TikTok/IG
   (complementary, not overlapping — YouTube still needed separately).

A third, softer idea worth borrowing: the **`stop_at` staged-task + FastAPI queue pattern**
(`task.py` + `controllers/v1/video.py`) to expose content-automation's `pipeline.py` as a REST
service with per-stage gates, rather than only the current `python3 src/pipeline.py` CLI.

### Concrete adaptation steps (no MPT runtime dependency)
1. Port `material.download_videos` → `content-automation/src/stock_sourcer.py` as an *optional
   visual provider* selectable per channel (`visual_mode: generate | stock | hybrid`). Reuse MPT's
   aspect/duration clipping logic; drop its MoviePy coupling (content-automation uses its own composer).
   Keys via `os.environ.get("PEXELS_API_KEY")` — never hardcoded.
2. Port `upload_post.cross_post_video` → `content-automation/src/crosspost.py`; wire into the
   pipeline's upload stage alongside the planned YouTube uploader. Config via env.
3. (Optional, later) Wrap `src/pipeline.py` in a thin FastAPI app mirroring MPT's `stop_at` gates
   to enable DQIII8/Telegram-triggered async jobs with progress polling.
4. Do **not** adopt MPT's LLM/TTS/subtitle/compose stages — content-automation's are superior or
   equivalent and already integrated with its bible-driven creative flow.

### Cost / tier alignment
- Stock sourcing (Pexels/Pixabay) is free-tier friendly → Tier C/B compatible.
- If MPT's *LLM* stage were ever used standalone, force `ollama` (C, $0) or `groq` (B, $0); never
  default to `openai`. content-automation already uses Groq for the bible — consistent.

---

## 7. Artifacts Inspected
`docker-compose.yml`, `Dockerfile`, `main.py`, `app/router.py`,
`app/controllers/v1/video.py`, `app/models/schema.py`, `app/services/task.py`,
`app/services/voice.py` (grep), `app/services/llm.py` (grep), `config.example.toml`.
Nothing from the cloned repo was installed or executed (read-only inspection only).
