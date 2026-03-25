# DQIII8 — AI Orchestration System

## Identity
DQ routes prompts to the cheapest capable model, enriching with domain knowledge.
Stack: Ollama qwen2.5-coder:7b ($0) → Groq llama-3.3-70b ($0) → Anthropic Sonnet (paid).
Root: /root/dqiii8 | DB: database/jarvis_metrics.db (47 tables) | 27 agents

## Pipeline (7 stages)
classify domain → select specialist → enrich knowledge → amplify intent → route tier → execute → learn

## Key Rules
- NEVER commit .env, database/*.db, or knowledge/*/PREMIUM_* to public repo
- ALWAYS run /simplify after generating code
- ALWAYS check tests before committing: python3 -m pytest tests/test_smoke.py -q
- Each project in my-projects/ has its OWN git repo — never commit to dqiii8 repo
- Use DQ_DEFAULT_TIER=groq+ollama — Sonnet only with --model sonnet flag

## Core Files
| File | Function |
|------|----------|
| bin/core/openrouter_wrapper.py | Main router (986 lines) |
| bin/agents/domain_classifier.py | Domain classification |
| bin/agents/knowledge_enricher.py | RAG retrieval + blacklist |
| bin/agents/domain_agent_selector.py | Keyword agent routing |
| bin/agents/confidence_gate.py | Selective enrichment |
| bin/agents/intent_amplifier.py | Prompt restructuring |
| bin/agents/working_memory.py | SQLite session context |
| bin/monitoring/ml_selector.py | Smart tier predictor |
| bin/monitoring/health_watchdog.py | 8 daily checks + Telegram |
| bin/monitoring/cost_tracker.py | Savings vs all-Sonnet |
| bin/ui/dashboard.py | FastAPI dashboard (port 8080) |

## Services (systemd)
jarvis-bot, dq-dashboard, autoreporte, ollama

## CLI
dq "prompt" → Groq ($0) | dq --model sonnet "prompt" → Sonnet | dq --classify "prompt" → debug

## Projects (each has own git repo)
- my-projects/auto-report/ → DPI scoring + DOCX generation
- my-projects/automatic-nutrition/ → Meal planning with LLM
- my-projects/sentiment-analysis/ → Business challenge project

## Skills auto-invocation
- When errors detected → /audit
- When session long (>50 turns) → /handover
- After significant code changes → /simplify then /checkpoint
- When importing anthropic SDK → /claude-api loads automatically
- When security-sensitive code detected → invoke security-audit agent

## Feedback loops
Every query logs to: routing_feedback (tier accuracy), knowledge_usage (chunk quality), instincts (pattern learning)
Weekly: routing_analyzer, knowledge_quality. Daily: health_watchdog. Monthly: memory_decay, lessons_consolidator.

## Context management
Compact at 80% with: /compact retain pipeline architecture, agent routing, and current task state
Never lose: DQIII8_ROOT path, current project context, test results
