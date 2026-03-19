# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |

Only the `main` branch receives security fixes. Older tags are not maintained.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately via GitHub's built-in security advisory tool:

1. Go to the **Security** tab of this repository
2. Click **Report a vulnerability**
3. Provide a clear description, reproduction steps, and potential impact

We will acknowledge your report within **48 hours** and aim to release a fix within **14 days** for critical issues.

## Scope

This repository contains an AI agent framework (DQIII8). The following are in scope:

- Command injection via crafted prompts or tool inputs
- Privilege escalation in the 3-layer permission supervisor
- Secrets or credentials exposed in code, logs, or output files
- Unsafe shell execution in hooks (`pre_tool_use.py`, `permission_request.py`, etc.)
- Path traversal in knowledge indexer or file-access tools

The following are **out of scope**:

- Vulnerabilities in third-party models or APIs (Anthropic, Groq, OpenRouter, Ollama)
- Issues that require physical access to the host machine
- Social engineering attacks against the repository owner

## Security Design Notes

- API keys and secrets are loaded exclusively from `.env` files, which are git-ignored
- The permission supervisor (`permission_analyzer.py`) enforces a 3-layer approval model for autonomous operations
- Destructive shell commands are blocked by default and require explicit human escalation via Telegram
- No credentials are ever written to source-controlled files

## Disclosure Policy

We follow coordinated disclosure. Once a fix is merged, we will publish a GitHub Security Advisory crediting the reporter (unless they prefer to remain anonymous).
