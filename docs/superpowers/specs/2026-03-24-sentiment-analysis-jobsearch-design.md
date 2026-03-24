# Sentiment Analysis Model — AI Job Search Platform
**Date:** 2026-03-24
**Status:** Approved
**Location:** `my-projects/sentiment-jobsearch/`

---

## 1. Purpose

A sentiment analysis system that interprets free-text and conversational inputs from job-seeking candidates on an AI-based job search platform. The model produces two outputs per synthesis cycle:

- A **structured JSON profile** consumed by the AI matcher and job scrapers to refine job recommendations
- A **Markdown coaching report** readable by human reviewers and candidates

The system closes a feedback loop: the more a candidate interacts with the bot, the more precisely the platform targets roles that will result in employer contact — and the more actionable coaching the candidate receives to improve their match rate.

---

## 2. Architecture Overview

```
Candidate Input (any type)
        │
        ▼
┌─────────────────────────┐
│   Real-time Classifier  │  ← lightweight model, runs on every message
│  - sentiment score      │    domain-context-aware
│  - emotion tag          │
│  - confidence level     │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   Session Signal Store  │  ← in-memory list of tagged turns
└──────────┬──────────────┘
           │
           │        ┌──────────────────────────────────────┐
           │        │   Explicit Match Feedback Layer       │
           │        │                                       │
           │        │  Structured rating:                   │
           │        │   GOOD → good / moderate / fair       │
           │        │   BAD  → inadequate / related         │
           │        │                                       │
           │        │  Free text → targeting directives     │
           └────────┤                                       │
                    └──────────────┬───────────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────┐
                    │   LLM Synthesis Engine  │
                    │  - session signals      │
                    │  - match feedback       │
                    │  - candidate background │
                    │  - long-term profile    │
                    └──────┬──────────┬───────┘
                           │          │
                           ▼          ▼
                      JSON Profile   Markdown Report
                           │
                           ▼
                    ┌──────────────────┐
                    │ Candidate Profile│  ← cumulative, evolves over time
                    └──────────────────┘
```

---

## 3. Components

### 3.1 Real-time Classifier
- **Model:** `cardiffnlp/twitter-roberta-base-sentiment` (3-class: positive / neutral / negative)
- **Input:** single candidate message (any type)
- **Output per turn:**
  - `sentiment_score`: float -1.0 to +1.0 (mapped from model logits: negative → -1, neutral → 0, positive → +1)
  - `emotion_tag`: one of `confident | anxious | enthusiastic | disengaged | frustrated | neutral`
  - `confidence`: float 0.0 to 1.0
  - `domain_context`: auto-detected field tag (finance, tech, healthcare, creative, etc.)
- **Emotion tag derivation:** the base model outputs positive/neutral/negative. The `emotion_tag` is derived by a secondary rule-based mapping that combines the sentiment class with keyword signals in the message text (e.g. positive + hedging language → `anxious`; positive + action verbs → `enthusiastic`; negative + comparative language → `frustrated`). This mapping is defined in a configurable rules file and can be updated without retraining.
- **Key constraint:** output is always interpreted relative to candidate background and seniority — a junior candidate expressing uncertainty is not the same signal as a senior candidate doing the same.

### 3.2 Session Signal Store
- In-memory list, one entry per candidate turn
- Each entry: `{ timestamp, input_type, raw_text, classifier_output, domain_tag }`
- Input types: `chat | bio | reaction | feedback`
- Serialized at session end for synthesis or fallback storage

### 3.3 Match Feedback Layer
- Accepts two inputs per feedback event:
  - **Structured rating:** `GOOD (good / moderate / fair)` or `BAD (inadequate / related)`
  - **Free text:** candidate's own words about what they want changed
- Free text parsed by LLM into **targeting directives** — discrete, actionable signals:
  - `prefer`, `avoid`, `salary_signal`, `location`, `seniority_preference`, `domain_focus`
- Explicit feedback is weighted higher than passive sentiment signals

### 3.4 LLM Synthesis Engine
- Triggered at session end or on a scheduled interval
- Single LLM call with structured prompt containing:
  - Full session signal list
  - Match feedback events
  - Candidate background (domain, seniority, skills)
  - Existing candidate profile (if returning user)
- Produces both outputs in one call:
  - JSON profile patch → merged into Candidate Profile Store
  - Markdown coaching report → saved as timestamped file

### 3.5 Candidate Profile Store
- Flat JSON file per candidate (one file = one candidate)
- Cumulative: each synthesis cycle merges new signals into existing profile
- Never overwritten on a failed synthesis cycle
- Upgradeable to a database without changing upstream components

---

## 4. Data Flow

```
1. Candidate sends message (any input type)
2. Classifier tags it → appended to Session Signal Store
3. [If match reaction] → also logged to Match Feedback Layer
4. [Session ends OR every 10 messages OR explicit user action triggers synthesis] →
   LLM Synthesis Engine receives all inputs
5. LLM produces JSON patch + Markdown report in one call
6. JSON merged into Candidate Profile Store
7. Markdown saved as: reports/[candidate_id]/report_[timestamp].md
8. JSON read by: job scraper + AI matcher
   Markdown read by: human reviewer + candidate
```

---

## 5. Output Formats

### JSON Profile (machine-readable)
```json
{
  "candidate_id": "string",
  "background": {
    "domain": "string",
    "seniority": "junior | mid | senior",
    "skills": ["string"]
  },
  "sentiment_trend": "improving | stable | declining",
  "emotion_profile": {
    "dominant": "string",
    "secondary": "string"
  },
  "targeting_directives": {
    "prefer": ["string"],
    "avoid": ["string"],
    "salary_signal": "string",
    "location": "string",
    "seniority_preference": "string",
    "domain_focus": "string"
  },
  "match_quality_history": [
    {
      "date": "ISO8601",
      "rating": "good | moderate | fair | inadequate | related",
      "note": "string"
    }
  ],
  "coaching_flags": ["string"],
  "last_updated": "ISO8601"
}
```

### Markdown Report (human-readable)
```
# Candidate Sentiment Report — [date]

## Engagement Summary
How the candidate communicated this session.

## Emotional Profile
Dominant patterns detected and what they signal for job search.

## Match Quality Feedback
What they responded to positively/negatively and why.

## Targeting Directives
Specific job search parameters updated this cycle.

## Coaching Recommendations
Concrete actions the candidate can take to increase their match rate.
```

---

## 6. Error Handling

| Failure Point | Behavior |
|---|---|
| Classifier fails on a message | Log error, tag turn as `unclassified`, continue session. Synthesis informed via flag. |
| LLM synthesis fails | Preserve session signals. Retry once. On second failure, write raw signals to fallback file. Existing profile never overwritten. |
| Ambiguous free text feedback | Flag as `needs_clarification` in JSON. Never guess. Human reviewer or follow-up bot prompt resolves it. |
| Match Feedback Layer LLM parse fails | Log error, store raw free text as `raw_feedback_unparsed` in the session signal. Synthesis engine includes it as unstructured context. No targeting directives written for that event. |

---

## 7. Testing

| Level | Approach |
|---|---|
| Unit | Fixed diverse sample inputs (finance PhD, bootcamp grad, career changer). Assert: (1) same input always produces the same output (deterministic), (2) sentiment scores fall within expected range [-1, +1], (3) emotion tags match expected values for known test cases, (4) domain context tag matches the input's field. |
| Integration | Synthetic session: 20 messages + 3 feedback events through full pipeline. Assert JSON and Markdown produced with all required fields. |
| Human spot-check | 5–10 Markdown reports reviewed per week at prototype stage to verify coaching recommendations are sensible and background-unbiased. |

---

## 8. Integration Interface

At prototype stage: **file-based**. JSON profile and Markdown reports are written to disk and read by other components or humans directly. Architecture is designed for a future upgrade path to:
- REST API microservice
- Database-backed profile store
- Streaming signals pipeline

---

## 9. Key Decisions & Rationale

| Decision | Rationale |
|---|---|
| Hybrid classifier + LLM | Cost-efficient: fast classifier on every message, LLM only for synthesis |
| Domain-context tagging | Diverse candidate backgrounds require context-relative interpretation |
| Explicit feedback weighted higher | Candidate stated intent is more reliable than inferred sentiment |
| Dual output (JSON + Markdown) | Serves both AI consumers and human reviewers from day one |
| Fail-safe per layer | No single failure corrupts the cumulative profile |
| File-based integration first | Keeps prototype flexible; readable by both humans and AI without infrastructure |
