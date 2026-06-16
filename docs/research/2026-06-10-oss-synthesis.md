# OSS Synthesis — Adopt/Reject Decisions (2026-06-10)

Filter: **wu wei** — a pattern earns INTEGRATE only if it solves a problem DQIII8 measurably has,
at lower complexity than the current solution. Anything that adds a daemon, queue, or DB for an
unmeasured problem is DISCARD by default.

## Decision Table

| Pattern | Source | Verdict | Effort | What it replaces in DQIII8 | Risk |
|---|---|---|---|---|---|
| `TaskScheduler` daemon | Odysseus | **DISCARD** | high | cron + autonomous_loop.sh (already works) | new asyncio daemon + 4 SQLAlchemy tables |
| fastembed ONNX vector memory | Odysseus | **DISCARD** | medium | sqlite-vec bge-m3 1024-d (superior) | dim mismatch (384d != 1024d), adds ChromaDB |
| VRAM-aware cookbook | Odysseus | **DISCARD** | medium | tier ladder (different problem: cost-first API routing vs local GPU quant) | scope mismatch |
| MPT wholesale integration | MoneyPrinterTurbo | **DISCARD** | high | content-automation CIP v2 (already generates SDXL/Flux, superior to B-roll) | scope creep |
| MPT stock-footage sourcing | MoneyPrinterTurbo | **ADAPT** (deferred) | low | nothing — additive | 1 new env var (PEXELS_API_KEY), no DB change |
| MPT TikTok/Instagram upload | MoneyPrinterTurbo | **ADAPT** (deferred) | medium | nothing — additive | 1 new module, no DB change |
| ReAct planning loop | Hermes Agent | **DISCARD** | high | plan_compiler (deterministic, 0ms, 0 LLM calls) | replaces a cheaper solution |
| Tool registry (@tool/getattr) | Hermes Agent | **DISCARD** | medium | AGENT_ROUTING dict + domain_agent_map.json (already exists) | duplication |
| Error recovery inject-and-retry | Hermes Agent | **DISCARD** | medium | ril.py MAX_RIL_RETRY_DEPTH=2 (calibrated, stronger) | regression risk |
| Footprint Ladder doctrine | Hermes Agent | **INTEGRATE** (doc only) | zero | — adds doctrine, no code | none |
| `compute_next_run()` pure fn | Odysseus | contingent micro-note | trivial | — additive, deferred | none |
| `_http_embed_down` latch | Odysseus | contingent micro-note | low | per-call bge-m3 probe (latency) | deferred until logs show repeated stalls |

## Adopted into roadmap

1. **MPT stock-footage sourcing** (ADAPT, deferred): `material.download_videos()` as an optional
   per-channel visual provider in content-automation. Trigger: when CIP v2 needs external B-roll
   supplementation. Effort: 1 module + 1 env var. No daemon, no new DB.

2. **MPT staged FastAPI pattern** (ADAPT, deferred): expose `src/pipeline.py` as a FastAPI service
   with `stop_at` so each pipeline stage is independently callable. Trigger: when content-automation
   needs to decouple generation from rendering for async flows.

3. **Footprint Ladder doctrine** (Hermes, INTEGRATE, doc only): cross-reference in
   `.claude/rules/03_tiering_and_routing.md` — agents should grow capability only
   after measuring that the lighter version is insufficient. No code change.

## Explicitly rejected (everything else)

- **Odysseus TaskScheduler**: solves cron inside Python; `autonomous_loop.sh` + systemd already
  does this at lower complexity and with zero new dependencies.
- **Odysseus/fastembed memory**: 384-d ONNX vs 1024-d bge-m3 — dimensional incompatibility alone
  is disqualifying; DQIII8's hybrid search (vector+FTS5+RRF) is already more complete.
- **Odysseus VRAM cookbook**: DQIII8 is single-Ollama on a VPS; quant/placement scoring is YAGNI
  until a multi-GPU setup exists.
- **MPT wholesale**: content-automation already generates visuals; importing MPT's full stack would
  regress from SDXL/Flux generation to stock B-roll.
- **Hermes ReAct loop**: `plan_compiler` is deterministic (0ms, 0 LLM calls) and derived from
  160-report production evidence. A probabilistic ReAct loop would be a step backward.
- **Hermes tool registry**: DQIII8 has `AGENT_ROUTING` + `domain_agent_map.json`; the pattern
  is already present.
- **Hermes error recovery**: `ril.py` with `MAX_RIL_RETRY_DEPTH=2` and structured `FailureContext`
  is demonstrably stronger than inject-traceback-and-retry.
