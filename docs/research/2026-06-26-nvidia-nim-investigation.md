# NVIDIA NIM — Investigación Completa
> Fecha: 2026-06-26 | Autor: Claude Sonnet 4.6 + deep-research workflow (107 agentes, 3x adversarial verify)

## Resumen ejecutivo

NVIDIA NIM expone 121 modelos vía API OpenAI-compatible en `integrate.api.nvidia.com/v1`.
Sondeo real sobre la cuenta: **50 disponibles, 58 con 404, 9 timeout, 4 error**.
Key insight: **Mistral Large 3 675B responde en 0.3s de forma gratuita** — mejor modelo libre del ecosistema.
Tier gratuito: 40 RPM global, sin headers x-ratelimit, explícitamente para dev/test/research (no producción).

---

## 1. Categorías del ecosistema NIM (17+ áreas documentadas)

| Categoría | Descripción | Estado en cuenta |
|-----------|-------------|-----------------|
| LLMs | Chat, reasoning, instruction-following | ✅ 30+ disponibles |
| Vision Language Models (VLM) | Texto + imagen, tablas, vídeo | ✅ 4 disponibles |
| Safety & Moderation | NemoGuard, Llama-Guard, GLiNER-PII | ✅ 7 disponibles |
| Traducción | Riva Translate | ✅ 1 disponible |
| Reasoning | Nemotron Omni reasoning | ✅ 1 disponible (8s) |
| Embeddings (NeMo Retriever) | RAG, semantic search, clasificación | ❌ todos 404 hosted — deploy local vía Docker |
| Reranking | Mejora retrieval RAG +24% Recall@5 | ❌ 404 hosted — deploy local |
| Speech/Audio (Riva/Maxine) | STT, TTS, voice RAG | ❌ endpoints separados |
| Bioinformatics (BioNeMo) | Proteínas, genómica | ❌ endpoints separados |
| Medical Imaging (MONAI) | Segmentación, diagnóstico | ❌ endpoints separados |
| Visual Generative AI | Imagen/vídeo generation | Parcial (DiffusionGemma) |
| Simulation & Physics | Física computacional | ❌ endpoints separados |

---

## 2. Sondeo completo — 121 modelos (2026-06-26)

### ✅ DISPONIBLES (50 modelos confirmados)

| Modelo | Latencia | Categoría | Notas |
|--------|----------|-----------|-------|
| `google/gemma-2-2b-it` | 0.1s | LLM general | Muy ligero |
| `meta/llama-3.2-3b-instruct` | 0.1s | LLM general | |
| `meta/llama-guard-4-12b` | 0.1s | Safety | Content safety |
| `mistralai/ministral-14b-instruct-2512` | 0.1s | LLM general | |
| `nvidia/gliner-pii` | 0.1s | Safety | PII detection |
| `nvidia/ising-calibration-1-35b-a3b` | 0.1s | LLM general | |
| `nvidia/llama-3.1-nemoguard-8b-content-safety` | 0.1s | Safety | |
| `nvidia/llama-3.1-nemoguard-8b-topic-control` | 0.1s | Safety | Topic filtering |
| `nvidia/nemotron-content-safety-reasoning-4b` | 0.1s | Safety | |
| `nvidia/nemotron-mini-4b-instruct` | 0.1s | LLM general | Muy ligero |
| `upstage/solar-10.7b-instruct` | 0.1s | LLM general | |
| `google/gemma-3n-e2b-it` | 0.2s | LLM general | |
| `microsoft/phi-4-multimodal-instruct` | 0.2s | Vision | Texto + imagen |
| `mistralai/mistral-small-4-119b-2603` | 0.2s | LLM general | 119B a 0.2s |
| `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | 0.2s | Safety | |
| `nvidia/nemotron-3-content-safety` | 0.2s | Safety | |
| `nvidia/riva-translate-4b-instruct-v1.1` | 0.2s | Traducción | |
| `stepfun-ai/step-3.7-flash` | 0.2s | LLM general | |
| `stockmark/stockmark-2-100b-instruct` | 0.2s | LLM general | Especializado japonés |
| `bytedance/seed-oss-36b-instruct` | 0.3s | LLM general | ByteDance |
| `meta/llama-3.1-70b-instruct` | 0.3s | LLM general | |
| `meta/llama-3.2-90b-vision-instruct` | 0.3s | Vision | 90B vision |
| `meta/llama-4-maverick-17b-128e-instruct` | 0.3s | LLM general | **1M ctx** |
| `mistralai/mistral-large-3-675b-instruct-2512` | **0.3s** | LLM general | **675B, mejor libre** |
| `mistralai/mistral-nemotron` | 0.3s | LLM general | |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | 0.3s | LLM general | |
| `nvidia/nemotron-3-nano-30b-a3b` | 0.3s | LLM general | MoE 30B/3B activos |
| `nvidia/nemotron-nano-12b-v2-vl` | 0.3s | Vision | VLM |
| `nvidia/nvidia-nemotron-nano-9b-v2` | 0.3s | LLM general | |
| `sarvamai/sarvam-m` | 0.3s | LLM general | Indio multilingüe |
| `meta/llama-3.1-8b-instruct` | 0.4s | LLM general | |
| `nvidia/llama-3.1-nemotron-nano-vl-8b-v1` | 0.5s | Vision | VLM 8B |
| `nvidia/llama-3.3-nemotron-super-49b-v1.5` | 0.5s | LLM general | |
| `openai/gpt-oss-120b` | 0.5s | LLM general | 120B |
| `nvidia/nemotron-3.5-content-safety` | 0.6s | Safety | |
| `openai/gpt-oss-20b` | 0.6s | LLM general | |
| `nvidia/nemotron-3-super-120b-a12b` | 1.0s | LLM general | MoE 120B |
| `moonshotai/kimi-k2.6` | 1.1s | LLM general | |
| `deepseek-ai/deepseek-v4-flash` | 1.4s | LLM código | **1M ctx, código** |
| `z-ai/glm-5.1` | 1.6s | LLM general | |
| `meta/llama-3.3-70b-instruct` | 3.6s | LLM general | |
| `abacusai/dracarys-llama-3.1-70b-instruct` | 4.6s | LLM general | Fine-tuned |
| `meta/llama-3.2-11b-vision-instruct` | 4.9s | Vision | |
| `minimaxai/minimax-m3` | 5.3s | LLM general | |
| `stepfun-ai/step-3.5-flash` | 6.8s | LLM general | |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 8.0s | Reasoning | |
| `google/diffusiongemma-26b-a4b-it` | 9.6s | Vision | Diffusion |
| `qwen/qwen3.5-397b-a17b` | 10.1s | LLM general | **397B MoE** |
| `mistralai/mistral-medium-3.5-128b` | 10.5s | LLM general | |
| `qwen/qwen3-next-80b-a3b-instruct` | 32.9s | LLM general | Lento |

### ⚠️ CONFIRMADOS LENTOS — solo aptos para batch (retry con 120–300s)

| Modelo | Latencia real | Veredicto |
|--------|--------------|-----------|
| `google/gemma-4-31b-it` | **37.8s** | ✅ Disponible — solo batch/background |
| `minimaxai/minimax-m2.7` | **38.9s** | ✅ Disponible — reasoning model, respuesta en `reasoning_content` ⚠️ |
| `qwen/qwen3.5-122b-a10b` | **170.1s** | ✅ Disponible — solo tareas batch offline |
| `deepseek-ai/deepseek-v4-pro` | >90s | No testeado con >90s — descartado sync |
| `nvidia/nemotron-3-ultra-550b-a55b` | >120s | MoE masivo — posiblemente requiere >120s |

### ❌ IRRECUPERABLES — timeout >300s (paradójico: modelos pequeños sin prioridad)

| Modelo | Timeout | Diagnóstico |
|--------|---------|-------------|
| `nvidia/llama-3.1-nemotron-nano-8b-v1` | >300s | TLS OK, request llega, sin respuesta — deprioritizado |
| `microsoft/phi-4-mini-instruct` | >300s | Ídem — capacidad agotada o sin disponibilidad |
| `meta/llama-3.2-1b-instruct` | >300s | Ídem — los modelos pequeños son los menos prioritarios en NIM |

> **Nota paradójica:** modelos de 1B–8B tardan más que los de 675B en esta cuenta.
> Posible causa: los modelos pequeños tienen menor asignación de capacidad en el cluster shared.

### ❌ NO DISPONIBLES en esta cuenta (404) — 58 modelos

Categorías completas en 404:
- **Todos los embeddings**: `baai/bge-m3`, `nvidia/nv-embed-*`, `nvidia/nv-embedqa-*`, `snowflake/arctic-embed-l`
- **Todo código especializado**: `ibm/granite-*-code`, `bigcode/starcoder2-15b`, `meta/codellama-70b`, `deepseek-ai/deepseek-coder-6.7b`, `google/codegemma-*`, `mistralai/codestral-22b`
- **Modelos legacy**: `meta/llama2-70b`, `mistralai/mistral-7b-v0.3`, `mistralai/mistral-large`, `mistralai/mistral-large-2`
- **Writer Palmyra**: `writer/palmyra-fin-70b-32k`, `writer/palmyra-med-70b-32k`, `writer/palmyra-creative-122b`
- **Nemotron enterprise**: `nvidia/nemotron-4-340b-instruct`, `nvidia/nemotron-4-340b-reward`, `nvidia/llama-3.1-nemotron-ultra-253b-v1`

---

## 3. Hallazgos del deep research (107 agentes, verificación 3-0)

### Embeddings y reranking — disponibles vía Docker local

Los NIMs de embedding y reranking son 404 en el endpoint hosted gratuito pero **se despliegan localmente**:

```bash
# Deploy local embedding NIM
docker run --gpus all -p 8000:8000 \
  nvcr.io/nim/nvidia/nv-embedqa-e5-v5:latest

# Uso (OpenAI-compatible)
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
embeddings = NVIDIAEmbeddings(base_url="http://localhost:8000/v1")
```

Benchmark RAG financiero (FiQA, HotpotQA, NQ):
- Solo retrieval denso: Recall@5 = 0.5699
- + reranker (`llama-nemotron-rerank-vl-1b-v2`): Recall@5 = **0.7070** (+24%)
- + dense+sparse+reranking: Recall@5 = **0.7137**
- Latencia reranking: ~1.750ms por 500 passages en H100

### Nemotron Nano 3 — MoE para agentes

- 32B total, **3.6B parámetros activos** (velocidad de 4B, razonamiento de 32B)
- Optimizado para tool-calling, math, scientific reasoning, coding
- Licencia comercialmente permisiva (NVIDIA Open Model License)
- Candidato para sustituir `qwen2.5-coder:7b` en Ollama si latencia OK

### Pipeline Voice RAG (referencia arquitectónica)

6 modelos NIM en cadena para Q&A de voz sobre documentos:
```
STT (nemotron-speech-600M) →
Embed (llama-nemotron-embed-vl-1b) →
Rerank (llama-nemotron-rerank-vl-1b) →
VLM (nemotron-nano-12b-v2-vl) →
Reasoning (nemotron-3-nano-30b-a3b) →
Safety (llama-3.1-nemotron-safety-guard-8b-v3)
```
Aplicación dqiii8: análogo para procesamiento de docs de clientes en intl-reports.

### RAG financiero — notebook GitHub

`NVIDIA/GenerativeAIExamples` — `Chat_with_nvidia_financial_reports.ipynb`:
- Fuente: earnings reports NVIDIA FY2020–2024
- Stack: `NV-Embed-QA` + `Mixtral-8x7b-instruct` + `similarity_search()` con metadata
- Directamente adaptable a: intl-reports (fuentes intel), M&A (documentos financieros), football-value (datos históricos)

### Constraint producción

> "The free developer tier is explicitly limited to development, testing, and research — **not production**"

Para dqiii8 autónomo en producción: mantener Groq como camino principal. NIM = fallback + capacidades únicas (safety, vision, 675B).

---

## 4. Impacto en routing dqiii8

### Cambios aplicados (commits `5a525fa`, `18114ed`)

| Agente | Antes | Después |
|--------|-------|---------|
| `python-specialist` | Ollama/qwen | NIM/deepseek-v4-flash |
| `web-specialist` | Ollama/qwen | NIM/deepseek-v4-flash |
| `algo-specialist` | Ollama/qwen | NIM/deepseek-v4-flash |
| `research-analyst` | Groq/llama-3.3-70b | NIM/mistral-large-3-675b |
| `software-specialist` | Groq/llama-3.3-70b | NIM/mistral-large-3-675b |
| `data-specialist` | Groq/llama-3.3-70b | NIM/mistral-large-3-675b |
| `ai-ml-specialist` | Groq/llama-3.3-70b | NIM/mistral-large-3-675b |
| `code-reviewer` | OpenRouter/gpt-oss-120b:free | Anthropic/claude-opus-4-8 |
| `code-validator` | (nuevo) | Anthropic/claude-opus-4-8 |
| `safety-checker` | (nuevo) | NIM/nemoguard-8b-content-safety |
| `content-safety` | (nuevo) | NIM/llama-guard-4-12b |
| `pii-detector` | (nuevo) | NIM/gliner-pii |
| `vision-specialist` | (nuevo) | NIM/phi-4-multimodal |
| `translate-specialist` | (nuevo) | NIM/riva-translate-4b-v1.1 |
| `nutrition-specialist` | NIM/palmyra-med (404) | Groq/llama-3.3-70b |

### Tier B+ — NIM default

`mistralai/mistral-large-3-675b-instruct-2512` — 675B a 0.3s, $0.
Fallback chain: `groq → nim → openrouter → github → pollinations`

### Deuda técnica identificada

| Item | Descripción | Prioridad |
|------|-------------|-----------|
| RAG embeddings local | Docker `nv-embedqa-e5-v5` + reranker para intl-reports intel | Media |
| `nemotron-3-nano-omni-30b-a3b-reasoning` | Candidato `logic-specialist` (8s, disponible) | Baja |
| NIM producción rate | Monitorizar 429s — si >10% en autónomo → escalar a paid | Alta |
| `qwen3-next-80b` (32.9s) | Solo apto para batch/background, no routing síncrono | Baja |

---

## 5. Modelos destacados por caso de uso dqiii8

| Caso de uso | Modelo recomendado | Latencia | Tier |
|-------------|-------------------|----------|------|
| Análisis financiero M&A | `mistralai/mistral-large-3-675b` | 0.3s | B+ |
| Generación código desde pseudocódigo | `deepseek-ai/deepseek-v4-flash` | 1.4s | B+ |
| Revisión estricta código | `claude-opus-4-8` | ~3s | S |
| Safety gate outputs | `nvidia/llama-guard-4-12b` | 0.1s | B+ |
| PII en documentos clientes | `nvidia/gliner-pii` | 0.1s | B+ |
| Análisis de imágenes/docs | `microsoft/phi-4-multimodal-instruct` | 0.2s | B+ |
| Traducción | `nvidia/riva-translate-4b-instruct-v1.1` | 0.2s | B+ |
| Razonamiento largo/complejo | `qwen/qwen3.5-397b-a17b` | 10.1s | B+ |
| Draft rápido barato | `mistralai/ministral-14b-instruct-2512` | 0.1s | B+ |
| Orquestación agentes | `nvidia/nemotron-3-nano-30b-a3b` | 0.3s | B+ |

---

*Fuentes: probe directo API, NVIDIA Developer Forums, docs.nvidia.com/nim, github.com/NVIDIA/GenerativeAIExamples, deep-research workflow 107 agentes (1.7M tokens)*
