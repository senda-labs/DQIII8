# Privacy Policy

**Effective date:** 2026-03-19
**Project:** DQIII8 (senda-labs/DQIII8)

## Summary

DQIII8 is a self-hosted AI agent framework. By design, all processing runs on your own machine or VPS. We do not operate servers that receive your data.

## What we collect

**Nothing by default.** DQIII8 runs entirely on your infrastructure. No data is sent anywhere without your explicit action.

## Optional anonymous telemetry

DQIII8 includes an **opt-in** telemetry system. It is **disabled by default**.

To enable: add `DQIII8_TELEMETRY=true` to your `.env` file.

When enabled, the following anonymous data is collected weekly:

| Data | Example | Purpose |
|------|---------|---------|
| Tier distribution | "70% C, 20% B, 10% A" | Optimize routing |
| Success rates | "Tier C: 99.5%" | Improve reliability |
| Domain distribution | "40% applied_sciences" | Prioritize knowledge bases |
| Error type counts | "BashError: 5" | Fix common issues |
| Session count | "23 sessions/week" | Understand usage patterns |
| Health score | "91.1" | Track system quality |
| OS/Python/RAM | "Ubuntu 24.04, Python 3.12, 8GB" | Optimize requirements |
| Model performance per tier | "Tier C: 99.5% success, 450ms avg" | Optimize routing decisions |
| Escalation frequency | "B→A: 12 times/week" | Improve tier classification |
| Domain-tier mapping | "finance→Tier A: 95% success" | Better domain routing |
| Enrichment impact | "enriched: 98% vs plain: 94%" | Validate knowledge system |

**Never collected:** prompts, outputs, API keys, file names, paths, IP addresses,
or any personally identifiable information.

You can see exactly what would be sent before enabling:

```bash
python3 bin/telemetry.py --collect
```

You can disable telemetry at any time by removing `DQIII8_TELEMETRY=true` from `.env`.

## Third-party APIs

When you configure API keys (Anthropic, Groq, OpenRouter, etc.), your prompts are sent to those providers. Each provider has their own privacy policy:

- [Anthropic Privacy Policy](https://www.anthropic.com/privacy)
- [Groq Privacy Policy](https://groq.com/privacy-policy/)
- [OpenRouter Privacy Policy](https://openrouter.ai/privacy)

DQIII8 never stores prompts or API responses in ways that could be accessed by third parties.

## Local data storage

All operational data (metrics, sessions, errors) is stored in `database/dqiii8.db` on your machine. This file:
- Is excluded from git (listed in `.gitignore`)
- Has permissions set to 600 (owner read/write only) at startup
- Is never uploaded anywhere

## Your `.env` file

Your `.env` file contains API keys and is:
- Excluded from git (listed in `.gitignore`)
- Set to permissions 400 (owner read-only) at startup by `bin/db_security.py`
- Never shared with anyone

## Contact

If you have questions about privacy, open a GitHub issue or use the security reporting process described in [SECURITY.md](.github/SECURITY.md).
