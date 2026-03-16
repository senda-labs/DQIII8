-- P2f: Add cost tracking and model tier to agent_actions
ALTER TABLE agent_actions ADD COLUMN cost_eur REAL DEFAULT 0.0;
ALTER TABLE agent_actions ADD COLUMN model_tier INTEGER DEFAULT 0;
-- model_tier: 1=Ollama local, 2=Groq/OpenRouter free, 3=Claude API paid, 0=unknown
