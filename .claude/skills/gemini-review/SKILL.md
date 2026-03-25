---
name: gemini-review
description: Launch an efficiency audit on modified Python files using Aider + Gemini 2.0 Flash. Analyzes bugs, efficiency, readability, and security. Saves report to database/audit_reports/.
command: /gemini-review
allowed-tools: [Bash, Read]
user-invocable: true
---

# /gemini-review — Gemini Pro Code Reviewer

Launches an efficiency audit on unreviewed Python files using Aider + Gemini 2.0 Flash.

## Usage

```
/gemini-review              # Review all pending modified .py files
/gemini-review <file>       # Review a specific file
/gemini-review --check-only # See how many files are pending (without reviewing)
```

## What it does

1. Detects modified `.py` files in git that have not been reviewed yet (via DB).
2. Passes each file to Aider with the `gemini/gemini-2.0-flash` model.
3. Analyzes: bugs, efficiency, readability, security.
4. Saves Markdown report to `database/audit_reports/gemini_review_<ts>.md`.
5. Registers the review in `dqiii8.db` (table `audit_reports`).
6. Git push → report available in Obsidian in ~1 min.

## Requirements

- `GEMINI_API_KEY` configured in `$DQIII8_ROOT/.env`
- `aider` installed: `pip install aider-chat --break-system-packages`

## Auto-integration

Runs automatically at the end of sessions ≥15 min (via `stop.py`)
if there are pending files. The process runs in the background and does not block shutdown.

## Implementation

```bash
python3 bin/gemini_review.py $ARGUMENTS
```

<!-- TODO: bin/gemini_review.py does not exist — needs creation -->
