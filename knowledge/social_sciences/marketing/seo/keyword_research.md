# Keyword Research

## Search Intent Types (Google's classification)
| Intent | User goal | Content match | Example |
|--------|-----------|---------------|---------|
| Informational | Learn something | Blog, guide, video | "how to lose weight" |
| Navigational | Find specific site | Brand page, login | "facebook login" |
| Transactional | Buy / take action | Product page, pricing | "buy running shoes" |
| Commercial | Compare before buying | Review, comparison | "best running shoes 2025" |

Intent mismatch = low rankings regardless of optimization quality.

## Keyword Metrics

### Search Volume
- Monthly searches in target location/language
- Seasonal variations: use 12-month average
- Estimated from: Google Keyword Planner (free), Ahrefs, Semrush
- Rule: volume shown in tools is ±50% accurate; use for relative comparison

### Keyword Difficulty (KD)
```
KD = f(DA of ranking pages, number of backlinks, brand strength)
KD 0–20:  low competition, new sites can rank
KD 21–50: moderate, requires domain authority + content quality
KD 51–70: hard, strong backlink profile needed
KD 71–100: very hard, dominated by high-DA domains
```

## Long-Tail Strategy
```
Head terms: 1–2 words, high volume, high KD (e.g., "SEO")
Mid-tail:   3–4 words, medium volume, medium KD
Long-tail:  5+ words, low volume, low KD (e.g., "technical SEO checklist for ecommerce")
```
- Long-tail: 70% of all searches, higher conversion rate, faster to rank
- Strategy: rank long-tail first → build authority → attack head terms

## Topic Clusters (Pillar-Cluster Model)
```
Pillar page: broad topic, high volume (e.g., "SEO Guide")
  └─ Cluster: "Technical SEO"
  └─ Cluster: "Keyword Research"
  └─ Cluster: "Link Building"
  └─ (all cluster pages link back to pillar)
```
Internal linking signals topical authority to Google.

## TF-IDF Relevance
```
TF  = (occurrences of term in doc) / (total words in doc)
IDF = log(total docs / docs containing term)
TF-IDF = TF × IDF
```
- High TF-IDF: term is frequent in this doc but rare across the web → high relevance signal
- Use to identify semantically related terms missing from content

## Google Search Console Key Metrics
| Metric | Definition | Benchmark |
|--------|-----------|-----------|
| Impressions | Times URL shown in SERP | — |
| Clicks | Actual clicks from SERP | — |
| CTR | Clicks / Impressions | Position 1: ~30%, Position 3: ~10%, Position 10: ~2% |
| Average Position | Mean ranking position | <10 = first page |

```
CTR optimization: test title tags and meta descriptions (A/B via GSC)
Position 1–3 captures ~60% of all clicks for a query
```
