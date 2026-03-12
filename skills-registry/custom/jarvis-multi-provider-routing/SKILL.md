---
name: jarvis-multi-provider-routing
version: 1.0.0
source: git-analysis/jarvis
analyzed_commits: 50
analyzed_date: 2026-03-12
repos: [/root/jarvis]
---

# JARVIS Multi-Provider Routing

## Patrón detectado

JARVIS usa un sistema de 3 tiers con fallback automático para enrutar prompts
al proveedor más barato que pueda resolver la tarea.

**Evidencia del historial:**
- `feat: routing unificado 3 tiers — Ollama+Groq+OpenRouter+Sonnet + j.sh Linux` (ba60bc7)
- `fix: CLAUDE.md Model Routing 3 tiers` (398cc6e, a407078) — 2 fixes en la misma sesión
- `feat: OpenRouter wrapper + routing 4 niveles` — iteración anterior
- Archivos que siempre cambian juntos: `bin/openrouter_wrapper.py` + `CLAUDE.md`

## Cuándo usar esta skill

- Añadir un nuevo proveedor de LLM a JARVIS
- Añadir un nuevo agente y asignarle modelo
- Debuggear por qué una llamada usa el tier incorrecto
- Añadir fallback a un provider existente

## Arquitectura de 3 tiers

```
Tier 1 — Local (gratis, sin latencia de red)
  Provider: Ollama
  Modelo:   qwen2.5-coder:7b
  Usar para: Python, refactor, debug, git ops

Tier 2 — Cloud gratis (latencia baja, rate limits)
  Provider: Groq → llama-3.3-70b-versatile    (review, analysis)
  Provider: OpenRouter → qwen3:free             (investigación/documentación)
  Provider: OpenRouter → nemotron:free          (video/TTS/media)
  Fallback chain: OpenRouter → Groq → llm7.io → Pollinations

Tier 3 — Cloud pagado (máxima capacidad, sin límites)
  Provider: Claude API → claude-sonnet-4-6
  Usar para: finanzas, creative writing, arquitectura, /mobilize
```

## Workflow: añadir nuevo proveedor

### 1. Añadir en `bin/openrouter_wrapper.py`

```python
PROVIDERS = {
    "nuevo-provider": {
        "base_url": "https://api.nuevo-provider.com/v1",
        "api_key_env": "NUEVO_PROVIDER_API_KEY",
        "headers_extra": {},
    },
    # ... providers existentes
}
```

### 2. Añadir al AGENT_ROUTING si es para un agente específico

```python
AGENT_ROUTING = {
    "mi-agente": ("nuevo-provider", "modelo-id"),
    # ...
}
```

### 3. Añadir al FALLBACK_CHAIN si debe ser fallback

```python
FALLBACK_CHAIN = {
    "openrouter": ["groq", "nuevo-provider", "llm7", "pollinations"],
    # ...
}
FALLBACK_MODELS = {
    "nuevo-provider": ("nuevo-provider", "modelo-fallback"),
    # ...
}
```

### 4. Añadir API key a `.env`

```bash
NUEVO_PROVIDER_API_KEY=sk-...
```

### 5. Actualizar CLAUDE.md § Model Routing

Añadir fila a la tabla con: Condition | Tier | Provider | Model

### 6. Verificar con classify

```bash
python3 bin/openrouter_wrapper.py classify "prompt de prueba"
# Salida: tier=N provider=X model=Y route=Z
```

## Archivos involucrados

| Archivo | Rol |
|---------|-----|
| `bin/openrouter_wrapper.py` | Core: PROVIDERS, AGENT_ROUTING, FALLBACK_CHAIN, stream_response() |
| `bin/ollama_wrapper.py` | Tier 1 local: llamadas a Ollama |
| `bin/j.sh` | Entry point CLI: flags --model local/groq/sonnet |
| `CLAUDE.md` | Tabla de routing documentada (siempre actualizar junto con wrapper) |
| `.env` | API keys: OPENROUTER_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY |

## Anti-patrones detectados (de commits fix:)

- **No actualizar CLAUDE.md junto con el wrapper** → `fix: CLAUDE.md Model Routing 3 tiers` (2 commits correctivos)
- **Hardcodear ANTHROPIC_API_KEY** en código Python → usar `os.getenv()` + `.env`
- **Llamar claude CLI desde dentro de Claude Code** → nested session error; usar OpenRouter o subprocess con env limpio
- **No implementar fallback** → si el provider falla sin fallback, el sistema se cae silenciosamente

## Clasificación automática

```python
# bin/openrouter_wrapper.py — classify subcommand
python3 bin/openrouter_wrapper.py classify "[prompt]"
# Retorna: tier=N provider=X model=Y route=Z
```

Keywords tier-1: python, refactor, debug, test, git, commit, script, bug, fix
Keywords tier-2: review, analiz, research, evaluar, audit, explica
Keywords tier-3: wacc, dcf, finanz, novel, xianxia, arquitectura, mobilize
