---
paths:
  - "bin/core/openrouter_wrapper.py"
  - "bin/core/providers/"
---
# NIM Provider — Reglas operacionales

## Qué es NIM en dqiii8

NVIDIA NIM es el Tier B+ del sistema de routing. API OpenAI-compatible en `integrate.api.nvidia.com/v1`.
Clave: `NVIDIA_API_KEY` en `.env`. Sondeo completo: **50/121 modelos operativos** (2026-06-26).
Fuente: `docs/research/2026-06-26-nvidia-nim-investigation.md` (reconciliado 2026-08-11 —
"52/121" era drift de este fichero; el doc de investigación original y
`03_tiering_and_routing.md` coinciden en 50/121). Nota: `NVIDIA_API_KEY` está actualmente
rechazada (403, confirmado 2026-08-11) — la clave debe reemitirse en build.nvidia.com antes
de poder re-sondear en vivo.

## Rate limits y comportamiento

- **40 RPM global** — compartido entre TODOS los modelos. No es por modelo.
- **Sin headers x-ratelimit** en responses — no hay señal anticipada de throttle.
- **429** → triggea fallback automático en `stream_response()` → siguiente en `FALLBACK_CHAIN`.
- **Tier gratuito = dev/test/research ONLY**, no producción. Para autónomo en producción: Groq es primario.
- Modelos pequeños (1B–8B) pueden tener latencia >300s — paradójico pero documentado.
- Modelos grandes MoE (Mistral 675B, Qwen 397B) responden más rápido que modelos pequeños.

## Modelos por categoría — solo los confirmados ✅

### LLM general (routing síncrono)
| Modelo | Latencia | Cuándo usar |
|--------|----------|-------------|
| `mistralai/mistral-large-3-675b-instruct-2512` | 0.3s | **DEFAULT NIM** — máxima calidad gratuita |
| `meta/llama-4-maverick-17b-128e-instruct` | 0.3s | Contexto largo (1M tokens) |
| `openai/gpt-oss-120b` | 0.5s | Alternativa calidad alta |
| `mistralai/mistral-small-4-119b-2603` | 0.2s | Balance velocidad/calidad |
| `mistralai/ministral-14b-instruct-2512` | 0.1s | Draft rápido, tarea simple |
| `nvidia/nemotron-mini-4b-instruct` | 0.1s | Tarea muy simple, máxima velocidad |

### Código
| Modelo | Latencia | Cuándo usar |
|--------|----------|-------------|
| `deepseek-ai/deepseek-v4-flash` | 1.4s | **Único código disponible** — 1M ctx, pseudocódigo→impl |

> ⚠️ Todos los modelos código especializados (Granite, CodeLlama, Codestral, StarCoder, CodeGemma) son **404**.

### Safety / Moderation (todos <0.2s)
| Modelo | Uso |
|--------|-----|
| `nvidia/llama-3.1-nemoguard-8b-content-safety` | Gate de contenido general |
| `nvidia/llama-3.1-nemoguard-8b-topic-control` | Restricción temática |
| `meta/llama-guard-4-12b` | Content safety clasificación |
| `nvidia/gliner-pii` | Detección PII en texto |
| `nvidia/nemotron-content-safety-reasoning-4b` | Safety con razonamiento |
| `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | Safety avanzado |

### Vision
| Modelo | Latencia | Capacidad |
|--------|----------|-----------|
| `microsoft/phi-4-multimodal-instruct` | 0.2s | Texto + imagen, tablas |
| `meta/llama-3.2-90b-vision-instruct` | 0.3s | Vision 90B, alta calidad |
| `nvidia/nemotron-nano-12b-v2-vl` | 0.3s | VLM Nemotron |
| `meta/llama-3.2-11b-vision-instruct` | 4.9s | Vision estándar |

### Traducción
| Modelo | Latencia |
|--------|----------|
| `nvidia/riva-translate-4b-instruct-v1.1` | 0.2s |

### Solo batch (>30s — NO usar en routing síncrono)
| Modelo | Latencia | Nota |
|--------|----------|------|
| `google/gemma-4-31b-it` | 37.8s | |
| `minimaxai/minimax-m2.7` | 38.9s | Reasoning — respuesta en `reasoning_content`, NO en `content` |
| `qwen/qwen3.5-397b-a17b` | 10.1s | 397B MoE — aceptable para batch |
| `qwen/qwen3.5-122b-a10b` | 170.1s | Solo offline |

## Embeddings — NO disponibles en hosted endpoint

Todos los modelos de embedding son 404 en `integrate.api.nvidia.com`.
Para RAG con NIM embeddings → **deploy local vía Docker**:

```bash
docker run --gpus all -p 8000:8000 \
  nvcr.io/nim/nvidia/nv-embedqa-e5-v5:latest
# Endpoint local: http://localhost:8000/v1
```

Benchmark: embed + reranker (`llama-nemotron-rerank-vl-1b-v2`) → +24% Recall@5 en RAG financiero.
Ver notebook: `NVIDIA/GenerativeAIExamples/RAG/notebooks/langchain/Chat_with_nvidia_financial_reports.ipynb`

## Añadir nuevo agente a NIM

```python
# En AGENT_ROUTING (openrouter_wrapper.py):
"nuevo-agente": ("nim", "mistralai/mistral-large-3-675b-instruct-2512"),

# SIEMPRE verificar que el modelo responde antes de commitear:
curl -s --max-time 30 -X POST https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Authorization: Bearer $NVIDIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"<model-id>","messages":[{"role":"user","content":"OK"}],"max_tokens":5}'
```

## Manejo de errores NIM

```python
# stream_response() ya maneja:
# 429 → fallback automático al siguiente proveedor en FALLBACK_CHAIN
# 500/502/503 → ídem
# Sin respuesta (timeout) → ídem tras curl --max-time

# Fallback chain desde NIM:
# nim → groq → openrouter → github → pollinations
```

## Referencia investigación

Doc completo: `docs/research/2026-06-26-nvidia-nim-investigation.md`
