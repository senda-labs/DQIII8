---
name: transcript-learn
description: Extract knowledge from video transcripts (YouTube, courses, seminars, podcasts) and convert to DQ knowledge chunks, skills, or agent definitions. Accepts YouTube URLs or .txt transcript files. ONLY invoked explicitly by user — never auto-invoked.
command: /transcript-learn
allowed-tools: [Bash, Read, Write, Grep, Glob]
user-invocable: true
disable-model-invocation: true
---

# /transcript-learn — Video Knowledge Ingestion

Extract structured knowledge from video transcripts and integrate into DQIII8.

## Usage

```
/transcript-learn <youtube-url>
/transcript-learn <path-to-transcript.txt>
/transcript-learn --batch <file-with-urls.txt>
```

## Pipeline

### Step 1: Get transcript

- If YouTube URL: use youtube-transcript MCP tool `get_transcript` (without timestamps for long videos)
- If .txt file: read directly
- If transcript > 25000 tokens: process in a forked subagent to save context

### Step 2: Analyze content

Extract from the transcript:

1. **Key concepts** — main ideas, definitions, frameworks
2. **Techniques/methods** — actionable processes, step-by-step workflows
3. **Tools/technologies** — software, libraries, APIs mentioned
4. **Data/metrics** — numbers, benchmarks, comparisons
5. **Quotes** — notable statements with timestamp if available
6. **Action items** — things we could implement in DQ or projects

### Step 3: Classify domain

Map content to DQ domain:

- `formal_sciences`: math, logic, algorithms, statistics
- `natural_sciences`: biology, physics, chemistry, nutrition
- `social_sciences`: finance, marketing, law, economics
- `humanities_arts`: writing, philosophy, history, design
- `applied_sciences`: programming, devops, web dev, AI/ML

### Step 4: Generate output

Based on content type, generate ONE OR MORE of:

**A) Knowledge chunk** (factual knowledge):
Save to: `knowledge/{domain}/{topic_slug}.md`
Format: use template `templates/knowledge_chunk.md`

**B) Skill proposal** (workflow/methodology):
Save to: `skills-registry/custom/proposed/{skill_name}.md`
Format: standard SKILL.md with frontmatter
Status: `PENDING_REVIEW`

**C) Agent proposal** (deep expertise):
Save to: `.claude/agents/proposed/{agent_name}.md`
Format: standard agent .md with frontmatter
Status: `PENDING_REVIEW` — user must approve before activation

### Step 5: Index

After saving knowledge chunk:
- Add to the domain's `index.json` if it exists
- Print summary of what was generated

### Step 6: Report

Print:

```
=== TRANSCRIPT LEARNING COMPLETE ===
Source: {url or file}
Duration: {if known}
Domain: {classified domain}
Generated:
  Knowledge chunks: N (paths listed)
  Skill proposals: N (paths listed)
  Agent proposals: N (paths listed)

Review pending items with: ls skills-registry/custom/proposed/
```

## Templates

- Knowledge chunks: `.claude/skills/transcript-learn/templates/knowledge_chunk.md`
- Skill proposals: `.claude/skills/transcript-learn/templates/skill_proposal.md`

## Notes

- This skill NEVER auto-invokes. User must explicitly type `/transcript-learn`
- For videos > 60 min, use subagent (context: fork) to avoid filling main context
- Knowledge chunks go to `knowledge/` (existing DQ structure)
- Proposed skills/agents go to `proposed/` subdirectories (not active until approved)
- All generated content includes source attribution
