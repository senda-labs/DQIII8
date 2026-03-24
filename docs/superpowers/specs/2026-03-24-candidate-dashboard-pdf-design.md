# Candidate Dashboard PDF — Design Spec
**Date:** 2026-03-24
**Status:** Approved
**Project:** `my-projects/sentiment-jobsearch/`
**Parent spec:** `docs/superpowers/specs/2026-03-24-sentiment-analysis-jobsearch-design.md`

---

## 1. Purpose

Replace the plain Markdown coaching report with a structured, visually clear PDF dashboard that a candidate (or reviewer) can read at a glance. The dashboard surfaces three equally weighted views of the candidate's state:

1. **Match Overview** — how well they fit the roles being shown
2. **Candidate Profile** — how the AI sees them (emotions, authenticity, targeting)
3. **Skill Analysis** — full skill breakdown with claimed vs inferred levels
4. **Coaching Actions** — concrete next steps to increase match rate

The PDF is generated at the end of every synthesis cycle and saved to disk. During the testing phase the caller sends it via Telegram. In the final product it will be served by a web app. The generator has no delivery dependency — it returns a file path and nothing else.

---

## 2. Architecture

```
JSON Profile (candidate_id/profile.json)
        │
        ▼
┌─────────────────────────┐
│   dashboard/generator.py│  ← entry point, called by synthesis pipeline
│   - reads JSON profile  │
│   - scans past profiles │    (for trend data)
│   - assembles 4 pages   │
│   - writes PDF to disk  │
│   - returns Path object │
└──────────┬──────────────┘
           │
    ┌──────┴──────┐
    │  pages/     │
    │  page_match.py     (Page 1)
    │  page_profile.py   (Page 2)
    │  page_skills.py    (Page 3)
    │  page_coaching.py  (Page 4)
    └─────────────┘
           │
           ▼
  dashboards/[candidate_id]/dashboard_[timestamp].pdf
           │
           ├── [testing]  → caller sends via notify.py / Telegram
           └── [web app]  → served as download or inline render
```

---

## 3. File Structure

```
sentiment-jobsearch/
├── dashboard/
│   ├── __init__.py
│   ├── generator.py          # entry point — takes profile path, returns PDF path
│   ├── utils.py              # shared: colors, fonts, draw helpers, gauge renderer
│   └── pages/
│       ├── __init__.py
│       ├── page_match.py     # Page 1: match score + history
│       ├── page_profile.py   # Page 2: emotion, authenticity, sentiment, targeting
│       ├── page_skills.py    # Page 3: skill table with bars and evidence
│       └── page_coaching.py  # Page 4: coaching flags + gap closers
├── dashboards/
│   └── [candidate_id]/
│       └── dashboard_[ISO8601_timestamp].pdf
├── profiles/                 # existing JSON profiles
├── reports/                  # existing Markdown reports (kept, not replaced)
└── tests/
    └── test_dashboard.py
```

---

## 4. Pages

### Page 1 — Match Overview

| Element | Description |
|---|---|
| Header band | Candidate name, domain, seniority, `last_updated`, session count |
| Match score gauges | Horizontal bar per target role, colored green (≥75) / amber (50–74) / red (<50) |
| Match score trend | Line chart: match score across sessions (x = session number, y = 0–100) |
| Match quality history | Table: last 5 entries — date / rating / note (truncated to 80 chars) |

### Page 2 — Candidate Profile

| Element | Description |
|---|---|
| Emotion profile | Dominant + secondary emotion as large styled text callouts |
| Authenticity score | Circular gauge, 0–1 scale, color-coded (green ≥0.8, amber 0.5–0.79, red <0.5) |
| Sentiment trend | Line chart across sessions (values: +1 improving / 0 stable / -1 declining) |
| Targeting directives | Two-column layout: prefer list (green bullets) / avoid list (red bullets) |

### Page 3 — Skill Analysis

One row per skill:

| Column | Content |
|---|---|
| Skill name | Bold label |
| Claimed level | Horizontal bar (grey), 1–5 scale. "—" if not claimed. |
| Inferred level | Horizontal bar (blue), 1–5 scale |
| Confidence | Percentage text |
| Gap note | Italic text in amber if gap exists, "—" if none |

Evidence bullets rendered below each skill row that has a gap. Collapsed (hidden) for skills with no gap. Skills sorted: no-gap first, then by gap size descending.

### Page 4 — Coaching Actions

| Element | Description |
|---|---|
| Coaching flags | Numbered list, prominent font size, top of page |
| Per-role gap closers | Role header → skill gap name → "current X/5 → required Y/5" → action text |
| Application angle | Blockquote-style callout per role (the recommended framing for applications) |

---

## 5. Visual Style

- **Palette:** white background, dark slate text (`#1a1a2e`), accent blue (`#2563eb`), green (`#16a34a`), amber (`#d97706`), red (`#dc2626`)
- **Typography:** matplotlib default sans-serif, sized consistently: title 16pt / section header 13pt / body 10pt / evidence 8pt
- **Layout:** each page uses matplotlib `axes` with `axis('off')` for text sections; chart axes for data visualizations
- **Page size:** A4 landscape (11.69 × 8.27 inches) for readability of the skill table
- **Margins:** 0.5in on all sides

---

## 6. Multi-Session Trend Data

No separate history store. The generator:

1. Scans `profiles/[candidate_id]/` for all timestamped JSON files
2. Reads `match_quality_history`, `sentiment_trend`, and `application_tailoring[*].match_score` from each
3. Sorts by `last_updated` to reconstruct chronological series
4. Passes the assembled series to the chart pages

If only one profile exists (first session): charts render a single point with a note "More sessions needed for trend data."

---

## 7. Generator Interface

```python
from pathlib import Path

def generate(profile_path: Path) -> Path:
    """
    Generate a candidate dashboard PDF from a JSON profile.

    Args:
        profile_path: absolute path to the candidate's JSON profile file

    Returns:
        Path to the generated PDF file

    Raises:
        FileNotFoundError: if profile_path does not exist
        ValueError: if the JSON profile is missing required top-level fields
    """
```

The caller is responsible for delivery (Telegram, web, file system). The generator does not import `notify.py`.

---

## 8. Error Handling

| Failure Point | Behavior |
|---|---|
| Missing field in JSON profile | Render placeholder "No data yet" for that element — never raise |
| No historical profiles found | Charts show single point + note, no trend line drawn |
| Matplotlib rendering error on a page | Log warning, skip that page, continue — partial PDF saved |
| PDF write fails | Raise exception — caller handles notification |
| Profile JSON unparseable | Raise `ValueError` immediately — caller handles |

---

## 9. Testing

| Level | Approach |
|---|---|
| Unit | Run `generate()` against the 3 existing PoC profiles (Elena, Col. Hayes, Priya). Assert: PDF file exists, size > 0, page count == 4. |
| Edge cases | (1) First-session profile — no history. (2) All skills at max — no gaps. (3) No targeting directives. (4) No match quality history entries. |
| Visual spot-check | Open generated PDFs manually to verify layout, readability, and color coding. No automated assertion on visual output. |

---

## 10. Delivery (Testing Phase)

During the testing phase, the synthesis pipeline calls `generate()` and then separately calls `notify.py` to send the returned PDF path via Telegram. This call lives in `poc_sentiment.py` (or the future synthesis module), not in `generator.py`.

```python
# in poc_sentiment.py — testing phase only
from dashboard.generator import generate
from bin.core.notify import send_document

pdf_path = generate(profile_path)
send_document(pdf_path, caption=f"Dashboard — {candidate_id}")
```

When the web app is built, the `send_document` call is replaced with the web delivery mechanism. The generator is unchanged.

---

## 11. Out of Scope

- Interactive dashboards (web, charts with hover/zoom)
- Automated visual regression testing
- Multi-language support
- Branding / custom logo
- Email delivery
