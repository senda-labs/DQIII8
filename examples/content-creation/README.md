# Example: Content Creation

This example shows how to configure DQIII8 for automated content pipelines — articles, video scripts, and social media posts.

## What this example covers

- Generating article drafts and blog posts
- Writing YouTube video scripts with TTS-ready formatting
- Creating social media captions and threads
- Running content pipelines end-to-end

## Project setup

```bash
# Set the active project
export JARVIS_PROJECT=content

# Use the content model (free OpenRouter tier)
export JARVIS_MODEL=openrouter/nvidia/nemotron-nano-12b-v2-vl:free

# Start a session
claude
```

## Example requests

```
"Write a YouTube script about the history of compilers, 8 minutes"
"Generate 5 Twitter thread ideas about machine learning for beginners"
"Create a blog post outline for 'Why Python won data science'"
"Write TTS-optimized narration for a video about neural networks"
```

## How DQIII8 routes content tasks

Content pipeline requests route to **Tier 1/2** (free models):

```
task_type=pipeline → agent=content-automator → tier=1 → nemotron-nano (free)
task_type=writing  → agent=creative-writer   → tier=3 → claude-sonnet-4-6
```

Use `writing` for high-quality literary content; `pipeline` for batch automation.

## Channel configuration

Define your channels in `context/youtube_channels.md`:

```markdown
## Channel: TechExplained
- Audience: developers, 25-40
- Tone: clear, concise, no jargon
- Duration: 8-12 minutes
- Style: whiteboard animation
```

DQIII8 injects channel context automatically when `JARVIS_PROJECT=content`.

## Pipeline structure

```
projects/content/
├── scripts/          # generated video scripts
├── audio/            # TTS output (ElevenLabs / local)
├── subtitles/        # SRT files
└── output/           # final rendered videos
```

## Running a full pipeline

```bash
python3 bin/run_pipeline.py \
  --topic "History of the Linux kernel" \
  --mode narrated \
  --duration 10 \
  --language en
```
