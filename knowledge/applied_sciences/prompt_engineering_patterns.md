---
domain: applied_sciences
agent: ai-ml-specialist
keywords_es: [prompt engineering, cadena pensamiento, few-shot, agente, RAG, evaluación, CoT, self-consistency, ReAct, fine-tuning, chunking, embedding]
keywords_en: [prompt, chain of thought, few-shot, agent, RAG, evaluation, CoT, self-consistency, ReAct, fine-tuning, chunking, embedding, LLM-as-judge]
---

# Prompt Engineering Patterns Reference

## 12 Core Patterns

| # | Pattern | Template | Use When | Cost vs Baseline |
|---|---------|----------|----------|-----------------|
| 1 | Zero-shot | "Classify as positive/negative: {text}" | Simple tasks; large capable model | 1x |
| 2 | Few-shot | 3–5 examples before task | Specific output format; rare task | 1x (longer context) |
| 3 | Chain-of-Thought (CoT) | "Let's think step by step..." | Math, logic, multi-step reasoning | 1x (more tokens) |
| 4 | Zero-shot CoT | Append "Think step by step" | Balance speed/accuracy; no examples | 1x |
| 5 | Self-Consistency | Generate N CoT answers, majority vote | High-stakes tasks; accuracy critical | Nx |
| 6 | Tree of Thoughts (ToT) | Multiple reasoning paths, evaluate, prune | Puzzles, planning, exploration tasks | 3–10x |
| 7 | ReAct | Thought → Action → Observation loop | Agents with tools; multi-step retrieval | Variable |
| 8 | PAL (Program-Aided Lang.) | "Write Python code to solve this..." | Numerical problems; exact computation | 1x + code exec |
| 9 | Self-Refine | Generate → Critique → Refine (3+ rounds) | Writing quality; structured output | 3x |
| 10 | Generated Knowledge | First: "List 5 facts about X" → Then answer | Knowledge-intensive questions | 2x |
| 11 | Least-to-Most | Break problem into subproblems; solve sequentially | Complex compositional tasks | 2–3x |
| 12 | Constitutional AI | Generate → Evaluate against principles → Revise | Safety; alignment; red-teaming | 2x |

## RAG vs Fine-tuning Decision Matrix

| Criterion | RAG | Fine-tuning | Hybrid |
|-----------|-----|-------------|--------|
| Data freshness | Excellent (update docs) | Poor (retrain needed) | Excellent |
| Factual grounding | Verifiable citations | No attribution | Verifiable |
| Latency | +100–500ms (retrieval) | Baseline | Higher |
| Cost | Retrieval infra | Training compute | Both |
| Style/format control | Poor | Excellent | Good |
| Hallucination risk | Lower (grounded) | Higher | Lower |
| Compute per inference | Higher | Baseline | Highest |
| Best for | Changing docs, Q&A, legal, medical | Tone, domain jargon, task specialization | Production systems |

## Chunking Strategies (for RAG)

| Strategy | How | Quality | Speed | Use When |
|----------|-----|---------|-------|---------|
| Fixed-size (e.g. 512 tokens) | Split at token boundary | Low (cuts sentences) | Fast | Homogeneous docs; prototype |
| Sentence-based | Split at sentence boundaries | Medium | Fast | General purpose |
| Recursive character split | Split at para/sentence/word hierarchically | Medium | Fast | LangChain default |
| Semantic splitting | Embed sentences; detect topic shifts | High | Slow (N embeds) | High-quality retrieval |
| Sliding window + overlap | Fixed size + 10–20% overlap | Medium | Medium | Reduce context boundary loss |
| Document-structure aware | Respect headers/sections/code blocks | High | Medium | Structured docs (MDX, PDF with sections) |

Overlap rule of thumb: 10–15% of chunk size (e.g. 50–100 tokens for 512-token chunks)
Chunk size heuristic: match to model context and query length; 256–512 for specific facts; 1024–2048 for synthesis

## Evaluation Metrics

| Metric | Measures | Score Range | When to Use |
|--------|---------|-------------|-------------|
| BLEU-4 | n-gram precision (weighted) vs reference | 0–1 (>0.4 = good for MT) | Machine translation; fixed reference tasks |
| ROUGE-1/2 | n-gram recall vs reference | 0–1 | Summarization; extractive tasks |
| ROUGE-L | Longest common subsequence | 0–1 | Summarization |
| BERTScore (F1) | Cosine similarity of contextual embeddings | 0–1 (>0.85 = good) | Open-ended generation; better human correlation |
| MoverScore | Earth Mover's Distance on embeddings | 0–1 | Summarization |
| G-Eval | LLM-as-judge with CoT rubric | 1–5 or 0–1 | State of the art; open-ended; expensive |
| RAGAS (RAG-specific) | Faithfulness, answer relevancy, context precision/recall | 0–1 each | RAG pipeline evaluation |
| LLM-as-judge | Direct scoring by strong LLM | custom scale | When ground truth unavailable |

**Faithfulness (RAGAS):** Does answer only use info from retrieved context? (hallucination check)
**Answer Relevancy (RAGAS):** Does answer address the question? (not just contextually faithful)

## System Prompt Architecture

```
[ROLE] You are {role_description}.

[CONTEXT] {relevant background}

[TASK] {specific task}

[CONSTRAINTS]
- Format: {output format}
- Length: {length constraint}
- Tone: {tone}
- Avoid: {anti-patterns}

[EXAMPLES] (if few-shot)
Input: {example_input}
Output: {example_output}

[INPUT]
{user_input}
```

Anti-patterns to avoid:
- "Do not..." → LLMs follow "do..." better; rephrase as positive instruction
- Vague quality descriptors: "good", "high-quality" → specify criteria explicitly
- Mixing multiple tasks in one prompt → separate with clear delimiters (XML tags, ----)
- Placing important instructions only at start → repeat key constraints at end for long prompts

## Model Selection Guide (2025)

| Task | Model Tier | Reasoning |
|------|-----------|-----------|
| Simple classification, extraction | Small (Haiku, GPT-4o-mini, Llama-3-8B) | cost-effective; no deep reasoning needed |
| Code generation, debugging | Medium (Sonnet, GPT-4o, Llama-3-70B) | strong coding benchmarks |
| Complex reasoning, architecture | Large (Opus, o3, Gemini Pro) | maximum reasoning; expensive |
| Real-time / latency-critical | Groq-hosted small models | ~500 tokens/sec; cheap |
| Local/private | Ollama (qwen2.5-coder, llama3) | no data leaves machine |

**Source:** Wei et al. (2022) "Chain-of-Thought Prompting" — arXiv:2201.11903 | Yao et al. (2023) "Tree of Thoughts" — arXiv:2305.10601 | Es et al. (2023) "RAGAS" — arXiv:2309.15217 | OpenAI Prompt Engineering Guide (platform.openai.com/docs/guides/prompt-engineering)
