# /prompt-optimize — Optimize a Prompt for DQIII8/Pipeline

Analyze and optimize a prompt for maximum effectiveness in the DQIII8 ecosystem
(LLM routing, scene director, TTS, Telegram bot, or agent instructions).

## Usage

```
/prompt-optimize [the prompt text or file path]
```

## Your Task

Given the prompt in `$ARGUMENTS`:

### 1. Classify the prompt type

- **LLM routing prompt** (sent to Ollama/Groq/Claude)
- **Image generation prompt** (sent to fal.ai flux-general)
- **TTS prompt** (narration text for ElevenLabs)
- **Agent instruction** (agent .md system prompt)
- **Telegram bot message** (user-facing output)

### 2. Evaluate on 5 dimensions (score 0-10 each)

| Dimension | What to check |
|-----------|---------------|
| **Clarity** | Unambiguous intent, no vague instructions |
| **Specificity** | Concrete examples, exact formats, numbers |
| **Conciseness** | No filler words, no redundant instructions |
| **Output contract** | Explicit format (JSON/markdown/text) stated |
| **Edge cases** | Handles empty input, failure, ambiguity |

### 3. Produce optimized version

Apply these DQIII8-specific improvements:

**For LLM prompts:**
- Add `Output ONLY JSON (no markdown):` if structured output needed
- Include exact field names in the output contract
- State the model tier this will run on (Haiku/Sonnet/Groq)

**For image prompts (fal.ai):**
- Lead with cinematographer style reference
- Include shot_type + camera_angle early in the prompt
- End with `no text no watermarks no logos`
- Keep under 200 tokens

**For TTS narration:**
- Present tense, max 8 words per sentence
- Include YOU/YOUR in at least 1 sentence
- Start with a specific name, date, or number
- Never start with "In [year]" / "During" / "Throughout"

**For agent instructions:**
- Add `## When NOT to use` section if missing
- Verify trigger keywords match CLAUDE.md delegation table
- Confirm model assignment matches 3-tier routing

**For Telegram messages:**
- Keep under 280 chars for readability
- Use `*bold*` for key metrics, `` `code` `` for commands
- No raw paths longer than 40 chars

### 4. Output format

```
PROMPT OPTIMIZATION REPORT
===========================
Type: [classified type]
Original score: [X]/50

Scores:
  Clarity:       [X]/10  — [one-line finding]
  Specificity:   [X]/10  — [one-line finding]
  Conciseness:   [X]/10  — [one-line finding]
  Output contract:[X]/10 — [one-line finding]
  Edge cases:    [X]/10  — [one-line finding]

Key issues:
  1. [issue + fix]
  2. [issue + fix]

Optimized prompt:
---
[full optimized prompt text]
---
Optimized score: [X]/50
```

## CRITICAL

- Do NOT change the semantic intent of the prompt
- Do NOT add hallucinated constraints (only what the system actually supports)
- Do NOT optimize for a different model tier than the one specified
- If the prompt is already ≥40/50 → report PASS with minor suggestions only

## User Input

$ARGUMENTS
