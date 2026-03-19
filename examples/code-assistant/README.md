# Example: Code Assistant

This example shows how to configure DQIII8 as a local-first coding assistant using Ollama.

## What this example covers

- Python code generation, refactoring, and debugging
- Git operations and commit message generation
- Running tests and fixing failures
- Code review with automated feedback

## Project setup

```bash
# Install Ollama and pull the coding model
ollama pull qwen2.5-coder:7b

# Set the active project
export JARVIS_PROJECT=my-project

# Use local model (free, no API key needed)
export JARVIS_MODEL=qwen2.5-coder:7b

# Start a session
claude
```

## Example requests

```
"Refactor this function to use pathlib instead of os.path"
"Write pytest unit tests for the UserService class"
"Debug why this async function hangs on large inputs"
"Review the latest commit and flag any security issues"
```

## How DQIII8 routes code tasks

Code requests automatically route to **Tier 1** (local Ollama) — no API costs:

```
task_type=code    → agent=python-specialist → tier=1 → qwen2.5-coder:7b (Ollama)
task_type=pipeline→ agent=python-specialist → tier=1 → qwen2.5-coder:7b (Ollama)
```

## Autonomous mode

Run coding tasks unattended with the 3-layer permission supervisor:

```bash
# Set objective for the autonomous session
echo "Refactor all db modules to use the Repository pattern" > tasks/current_objective.txt

# Start autonomous session
JARVIS_MODE=autonomous claude --dangerously-skip-permissions
```

The supervisor auto-approves safe operations and escalates destructive ones via Telegram.

## Git workflow

DQIII8 auto-commits `lessons.md` and project files at session end:

```bash
git log --oneline -5
# chore(auto): session a1b2c3d4 2026-03-19
# feat: implement repository pattern for db modules
```
