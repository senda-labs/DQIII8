# ADR-001 — Image-First Video Pipeline

**Date:** 2026-03-15
**Status:** Accepted
**Project:** content-automation
**Deciders:** Iker, JARVIS

---

## Context

The original pipeline generated narration text first (via NarrativeArchitect), then
generated images as an afterthought. This produced a fundamental misalignment:
images were forced to match pre-written text, rather than text describing what the
camera actually shows. The result was visual incoherence — narrations referenced
details not visible in the images, and images lacked a consistent visual identity.

Additionally, the original fal.ai model (`fal-ai/flux/dev`) lacked `negative_prompt`
and `reference_image_url` support, so each scene was generated independently with
no visual consistency between frames.

## Decision

Adopt an **image-first pipeline** where:
1. `SeriesDirector` (Sonnet) creates a `SeriesBible` — protagonist description,
   color palette, cinematographer reference — shared across ALL scenes.
2. `SceneArchitect` (Sonnet) designs full cinematographic parameters per scene
   (shot_type, camera_angle, character, action, location, foreground, background).
3. `ImagePromptBuilder` (deterministic, no LLM) assembles the fal.ai prompt from
   scene fields + SeriesBible.
4. `fal-ai/flux-general` generates each image with `negative_prompt` (eliminating
   artifacts) and `reference_image_url` (scene 0 URL for scenes 1-4, ensuring
   visual consistency).
5. Only AFTER the image exists does `ScriptWriter` (Haiku) write the narration text,
   constrained to describe what the camera actually shows.

The fal.ai model is permanently `fal-ai/flux-general`. The previous `fal-ai/flux/dev`
is forbidden.

## Consequences

**Positive:**
- Visual coherence: protagonist looks the same across all scenes
- Narration accuracy: text describes the actual generated image, not a hypothetical
- `negative_prompt` eliminates blurry faces, modern anachronisms, text overlays
- `reference_image_url` locks color palette and cinematographer style
- SceneViralScorer can check `image_coherence` (noun overlap between narration and visual_brief)

**Negative / Trade-offs:**
- Pipeline is ~33s longer per video (extra LLM calls + image-first sequencing)
- Scene 0 must complete before scenes 1-4 can start (to obtain reference URL)
- Changing narration style requires the image to already exist (less flexible)

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Text-first (original) | Narration describes what should be shown, not what is shown — visual mismatch |
| `fal-ai/flux/dev` | No `negative_prompt`, no `reference_image_url` — can't enforce visual consistency |
| Parallel text+image generation | No way to write narration about an image that doesn't exist yet |

---

## Invariants

```yaml
invariants:
  - id: "ADR-001-I1"
    description: "visual_matcher main t2i must use flux-general, not bare flux/dev"
    paths:
      - "backend/services/visual_matcher.py"
    must_contain:
      - "fal-ai/flux-general"
    must_not_contain:
      - "\"fal-ai/flux/dev\","
    message: "ADR-001 violation: visual_matcher.py main t2i endpoint must be fal-ai/flux-general, not fal-ai/flux/dev. Note: fal-ai/flux/dev/image-to-image is permitted as i2i fallback."

  - id: "ADR-001-I2"
    description: "NEGATIVE_PROMPT must be defined in visual_matcher"
    paths:
      - "backend/services/visual_matcher.py"
    must_contain:
      - "NEGATIVE_PROMPT"
    message: "ADR-001 violation: NEGATIVE_PROMPT constant must be defined in visual_matcher.py to suppress artifacts."

  - id: "ADR-001-I3"
    description: "scene_director must assign narration AFTER image exists (image-first order)"
    paths:
      - "backend/services/scene_director.py"
    must_contain:
      - "narration_text"
      - "image_url"
    message: "ADR-001 violation: scene_director.py must implement image-first flow — narration_text assigned after image_url is populated."

  - id: "ADR-001-I4"
    description: "scene_director must not call bare flux/dev t2i endpoint"
    paths:
      - "backend/services/scene_director.py"
    must_not_contain:
      - "\"fal-ai/flux/dev\","
    message: "ADR-001 violation: scene_director.py contains reference to deprecated fal-ai/flux/dev model."

  - id: "ADR-001-I5"
    description: "CLAUDE_PLANNER_MODEL must be claude-sonnet-4-6 in scene_director"
    paths:
      - "backend/services/scene_director.py"
    must_contain:
      - "CLAUDE_PLANNER_MODEL = \"claude-sonnet-4-6\""
    message: "ADR-001 violation: CLAUDE_PLANNER_MODEL in scene_director.py must be claude-sonnet-4-6 (Tier 3 orchestration for pipeline planning)."
```
