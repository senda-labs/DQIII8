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
JSON Profile (profiles/<candidate_id>/profile_<timestamp>.json)
        │
        ▼
┌─────────────────────────┐
│   dashboard/generator.py│  ← entry point, called by synthesis pipeline
│   - reads JSON profile  │
│   - scans past profiles │    (for trend data)
│   - assembles pages     │
│   - writes PDF to disk  │
│   - returns Path object │
└──────────┬──────────────┘
           │
    ┌──────┴──────┐
    │  pages/     │
    │  page_match.py     (Page 1)
    │  page_profile.py   (Page 2)
    │  page_skills.py    (Page 3, continuation Page 3b if >15 skills)
    │  page_coaching.py  (Page 4)
    └─────────────┘
           │
           ▼
  dashboards/<candidate_id>/dashboard_<timestamp>.pdf
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
│       ├── page_skills.py    # Page 3 (+3b if overflow): skill table with bars and evidence
│       └── page_coaching.py  # Page 4: coaching flags + gap closers
├── dashboards/
│   └── <candidate_id>/
│       └── dashboard_<ISO8601_timestamp>.pdf
├── profiles/
│   └── <candidate_id>/
│       └── profile_<ISO8601_timestamp>.json   # naming convention for all profile files
├── reports/                  # existing Markdown reports (kept, not replaced)
└── tests/
    └── test_dashboard.py
```

The generator creates `dashboards/<candidate_id>/` if it does not exist. It never raises on a missing output directory.

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

**Overflow rule:** A maximum of 15 skills fit on one A4 landscape page at the defined font sizes. If `skill_profile` contains more than 15 skills, `page_skills.py` renders Page 3 with skills 1–15 and inserts a continuation page (Page 3b) with the remainder. The PDF page count is therefore 4 or 5, not always exactly 4.

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

1. Derives `candidate_id` from `profile_path.parent.name` (the profile file lives at `profiles/<candidate_id>/profile_<timestamp>.json`, so the parent directory name is the candidate ID)
2. Scans `profiles/<candidate_id>/` for all files matching `profile_*.json`
3. Reads `match_quality_history`, `sentiment_trend`, and `application_tailoring[*].match_score` from each file
4. Sorts by the `last_updated` field inside each JSON to reconstruct chronological order
5. Passes the assembled series to the chart pages

If only one profile file exists (first session): charts render a single data point with a note "More sessions needed for trend data."

---

## 7. Generator Interface

```python
from pathlib import Path

def generate(profile_path: Path) -> Path:
    """
    Generate a candidate dashboard PDF from a JSON profile.

    Expected profile path structure:
        <project_root>/profiles/<candidate_id>/profile_<timestamp>.json

    Required top-level fields (raise ValueError if absent or None):
        - candidate_id (str)
        - background (dict with at least 'domain' and 'seniority')

    All other fields are optional. Missing optional fields render as
    "No data yet" placeholders — they never raise.

    Args:
        profile_path: absolute path to the candidate's JSON profile file

    Returns:
        Path to the generated PDF file

    Raises:
        FileNotFoundError: if profile_path does not exist
        ValueError: if the JSON is unparseable, or if 'candidate_id' or
                    'background' are absent or None in the parsed JSON
    """
```

The caller is responsible for delivery (Telegram, web, file system). The generator does not import `notify.py`.

---

## 8. Error Handling

| Failure Point | Behavior |
|---|---|
| `candidate_id` or `background` absent in JSON | Raise `ValueError` — these are required to produce a meaningful dashboard |
| Any other field missing in JSON profile | Render placeholder "No data yet" for that element — never raise |
| No historical profile files found | Charts show single point + note, no trend line drawn |
| Matplotlib rendering error on a page | Log warning, insert a placeholder page ("Page could not be rendered") — PDF always has the expected page count |
| PDF write fails | Raise `IOError` — caller handles notification |
| Profile JSON unparseable | Raise `ValueError` immediately — caller handles |

---

## 9. Testing

| Level | Approach |
|---|---|
| Unit | Run `generate()` against the 3 existing PoC profiles (Elena, Col. Hayes, Priya). Assert: PDF file exists, size > 0, page count >= 4 (allows for skill overflow page). Use `pypdf` (zero-config, pip-installable) to count pages. |
| Edge cases | (1) First-session profile — no history. (2) All skills at max — no gaps. (3) No targeting directives. (4) No match quality history entries. (5) More than 15 skills — assert page count >= 5. |
| Visual spot-check | Open generated PDFs manually to verify layout, readability, and color coding. No automated assertion on visual output. |

---

## 10. Delivery (Testing Phase)

During the testing phase, the synthesis pipeline calls `generate()` and then separately uses `notify.py` to send the PDF via Telegram.

`notify.py` currently only exposes `send_telegram(message)`. A `send_document(path, caption)` function must be added to `notify.py` as part of this implementation, using the Telegram Bot API `sendDocument` endpoint. This addition is in scope for the dashboard implementation task.

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
