---
name: skill-create
description: Analyzes the DQIII8 git history to extract patterns and generate SKILL.md files in skills-registry/custom/. Adapted version of ECC skill-create for the DQIII8 ecosystem.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /skill-create — Skill Generation from Git History

Analyzes DQIII8 repositories to extract real patterns and generate
reusable skills in `skills-registry/custom/`.

## Usage

```
/skill-create                        # Analyze /root/jarvis (last 50 commits)
/skill-create --commits 100          # More commits
/skill-create --repo <path>          # Analyze a specific repo path
/skill-create --repo all             # Analyze all configured repos
/skill-create --instincts            # Also generate instincts for continuous-learning
```

## What it does

1. **Parses git history** — real commits, changed files, co-change frequency
2. **Filters noise** — excludes: merge commits, "session handover", "gemini review", "auto-commit", stop hook
3. **Detects patterns** — repeated workflows, architecture, conventions
4. **Generates SKILL.md** — compatible with DQIII8 INDEX.md
5. **Updates INDEX.md** — adds the skill with status PENDING_REVIEW

## Analysis steps

### Step 1: Collect git data

```bash
REPO=${REPO:-$JARVIS_ROOT}
cd $REPO

# Significant commits (exclude noise)
git log --oneline -${COMMITS:-50} --no-merges \
  --pretty=format:"%H|%s|%ad" --date=short \
  | grep -v "session handover\|gemini review\|auto-commit\|chore(review)"

# Files that change together most often
git log --oneline -${COMMITS:-50} --name-only --pretty=format:"%s" \
  | grep -v "session handover\|gemini review\|^$\|^[a-f0-9]" \
  | sort | uniq -c | sort -rn | head -20

# Commit types
git log --oneline -${COMMITS:-50} --no-merges \
  | grep -v "session handover\|gemini review" \
  | cut -d' ' -f2- | sed 's/:.*$//' | sort | uniq -c | sort -rn
```

### Step 2: Detect patterns

| Pattern | Detection signal |
|---------|-----------------|
| **Multi-provider routing** | Changes in `bin/*_wrapper.py` + CLAUDE.md together |
| **Agent creation** | Changes in `.claude/agents/*.md` (2+ files at once) |
| **JAL workflow** | Changes in `bin/jal_*.py` (4 coordinated files) |
| **Hooks lifecycle** | Changes in `.claude/hooks/` + `bin/` together |
| **Commit conventions** | feat/fix/chore/docs prefixes with or without emoji |
| **Session patterns** | Frequency and structure of sessions/ |

### Step 3: Generate SKILL.md

Output in `skills-registry/custom/{skill-name}/SKILL.md`:

```markdown
---
name: {skill-name}
version: 1.0.0
source: git-analysis/{repo-name}
analyzed_commits: {count}
analyzed_date: {YYYY-MM-DD}
repos: [{repo-paths}]
---

# {Skill Name}

## Detected pattern
{pattern description with evidence from history}

## When to use this skill
{specific triggers}

## Workflow
{concrete steps with real repo examples}

## Files involved
{list of files typically touched}

## History examples
{real commits as evidence}

## Anti-patterns
{what to avoid, based on fix: commits}
```

### Step 4: Update INDEX.md

Add to `skills-registry/INDEX.md`:

```markdown
| {skill-name} | git-analysis/{repo} | ⏸ PENDING_REVIEW | — | {description} |
```

Required columns: `Skill | Source | Status | Approved by | Notes`

### Step 5 (optional): Generate instincts

If `--instincts`, also create `skills-registry/custom/{skill-name}/instinct.yaml`:

```yaml
---
id: {repo}-{pattern-id}
trigger: "{when it applies}"
confidence: 0.8
domain: {git|python|routing|agents}
source: git-analysis/{repo}
evidence_commits: {count}
---

# {Instinct Name}

## Action
{what to do}

## Evidence
- Analyzed: {n} commits in {repo}
- Frequency: {percentage}% of feat commits follow this pattern
```

## Repos analyzed

| Repo | Path | Focus |
|------|------|-------|
| dqiii8 | `$JARVIS_ROOT` | Infrastructure, agents, JAL, routing |

## Expected output

```
skills-registry/custom/
├── dqiii8-multi-provider-routing/
│   └── SKILL.md
├── dqiii8-agent-creation/
│   └── SKILL.md
└── {detected-name}/
    ├── SKILL.md
    └── instinct.yaml  # if --instincts
```

## Notes

- Output: `skills-registry/custom/` (NOT `~/.claude/skills/`)
- Initial status always: `⏸ PENDING_REVIEW`
- To approve: review → `✅ APPROVED` → add to combo in INDEX.md
- Prohibition: do not load skills from `cache/` without review (see jarvis-prohibitions.md)

---
*Adapted from ECC /skill-create for DQIII8*
