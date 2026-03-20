# Prompt Engineering Fundamentals

## Definition
Prompt engineering is the practice of designing and optimizing inputs to language models (LLMs) to reliably produce desired outputs. It is a combination of art and science — requiring understanding of how LLMs process language, their capabilities and limitations, and structured techniques for reliable generation.

## Core Concepts

- **Instruction Clarity:** Be specific and unambiguous. State the task, format, constraints, and audience explicitly. "Write a 3-paragraph professional email explaining X to a non-technical manager" outperforms "write an email about X."
- **Zero-Shot vs. Few-Shot Prompting:**
  - Zero-shot: No examples provided. Relies on pre-trained knowledge.
  - Few-shot: 2-5 labeled examples in the prompt demonstrate the desired format and reasoning.
  - Many-shot: Larger example sets for difficult tasks. More tokens = higher cost.
- **Chain-of-Thought (CoT):** "Think step by step" before answering. Forces the model to reason through intermediate steps, dramatically improving accuracy on math, logic, and complex reasoning tasks. Zero-shot CoT or few-shot with examples of reasoning.
- **System Prompts:** Set the model's role, tone, and constraints. "You are an expert Python developer. Always provide working code with type hints." System prompts persist across conversation turns.
- **Role Prompting:** "Act as a senior product manager reviewing a PRD." Persona priming shifts the model's response style toward the specified role's knowledge and communication style.
- **Output Format Control:** Specify JSON, Markdown, bullet lists, or code blocks. Use output schemas. "Respond ONLY with valid JSON with keys: {summary: string, sentiment: 'positive'|'negative'|'neutral', confidence: number}."
- **RAG (Retrieval-Augmented Generation):** Inject relevant retrieved documents into the prompt to ground responses in specific knowledge. Reduces hallucination, enables current information.
- **Temperature and Parameters:** Temperature controls randomness. 0.0 = deterministic, greedy. 1.0 = highly variable. Use low temperature for factual/code tasks; higher for creative tasks. Top-p (nucleus sampling) controls diversity.
- **Prompt Chaining:** Break complex tasks into sequential prompts. Output of one becomes input to the next. Reduces hallucination from trying to do too much at once.

## Common Failure Modes
- Hallucination: Model generates plausible-sounding but false information. Mitigate with RAG, verification steps, low temperature.
- Instruction following failures: Model ignores parts of the prompt. Add emphasis, repeat critical constraints, simplify.
- Context window limits: Long documents exceed context. Chunk and retrieve relevant sections.

## Practical Applications
- **Code generation:** "You are an expert Python developer. Implement X with error handling, type hints, and docstrings. Follow PEP8."
- **Data extraction:** Structured JSON output from unstructured text.
- **Classification:** Few-shot examples of categories.
- **Summarization:** Length constraints, audience specification, format requirements.
- **Agentic systems:** Prompts that orchestrate tool calls, planning, and multi-step reasoning.
