DQIII8 Weekly Audit — 2026-07-05
========================================
Actions (7d): 235 total, 26.0% success, 16967ms avg, 3 sessions

Routing by tier:
  Tier C: 149 calls, 34.9% ok, 26539ms
  Tier B: 86 calls, 10.5% ok, 384ms

Top errors (7d, unresolved):
  [174x] ESCALATION
  [43x] nimError
  [39x] openrouterError
  [38x] groqError
  [38x] githubError

Services DOWN: autoreporte

ALERTS (6):
  - Success rate dropped 97.4% → 26.0% (delta: -71.4pp)
  - New error type: nimError (43x) — nim/mistralai/mistral-large-3-675b-instruct-2512 failed — no
  - New error type: openrouterError (39x) — openrouter/qwen/qwen3-coder:free failed — no response or HTT
  - New error type: groqError (38x) — groq/llama-3.3-70b-versatile failed — no response or HTTP er
  - New error type: githubError (38x) — github/deepseek-v3-0324 failed — no response or HTTP error
  - New error type: pollinationsError (16x) — pollinations/openai failed — no response or HTTP error
Cost (7d): $0.00 actual, $2.80 baseline, saved $2.80 (100.0%)