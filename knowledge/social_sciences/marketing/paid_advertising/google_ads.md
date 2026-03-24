# Google Ads

## Core Formulas

### Quality Score (1–10)
```
QS = f(Expected CTR, Ad Relevance, Landing Page Experience)
Each component: Below Average / Average / Above Average
QS 7+ = discount on CPC; QS <4 = premium on CPC
```
- Expected CTR: historical CTR adjusted for position
- Ad Relevance: keyword match to ad copy
- Landing Page: relevance, load speed, mobile UX, content match

### Ad Rank
```
Ad Rank = QS × Max Bid + Ad Extension impact
```
- Determines position AND actual CPC paid
- Actual CPC = (Ad Rank of next advertiser / Your QS) + $0.01
- Extensions (sitelinks, callouts, structured snippets) increase Ad Rank at no cost

### ROAS
```
ROAS = Revenue from ads / Ad spend
```
- ROAS 4.0 = $4 revenue per $1 spent
- Target ROAS varies by industry: ecommerce typical 3–8×
- Breakeven ROAS = 1 / gross margin (50% margin → breakeven at 2.0 ROAS)

## Bidding Strategies
| Strategy | Use case | Control |
|----------|----------|---------|
| Manual CPC | Testing, tight control | Bid per keyword |
| Enhanced CPC | Manual + smart adjustments | Bid per keyword |
| Target CPA | Lead gen, known CPA target | Set target cost per acquisition |
| Target ROAS | Ecommerce with revenue tracking | Set target ROAS |
| Maximize Conversions | Budget-limited, learning phase | Budget only |
| Maximize Conversion Value | Ecommerce, optimize for revenue | Budget only |

Smart bidding requires ≥30–50 conversions/month for reliable learning.

## Campaign Structure
```
Account
└── Campaign (budget, geo, network, bidding strategy)
    └── Ad Group (theme, audience, bid)
        └── Keywords (match types)
            └── Ads (responsive search ads: 15 headlines, 4 descriptions)
```

### Keyword Match Types
| Type | Syntax | Trigger |
|------|--------|---------|
| Broad | keyword | Related searches, synonyms, variations |
| Phrase | "keyword" | Must contain phrase, in order |
| Exact | [keyword] | Exact or very close variants only |

- Broad match + Smart Bidding = Google's recommended default (2024)
- Exact match: highest control, lowest reach

## Performance Benchmarks (Google Ads industry averages)
- Search CTR: 2–5% (varies widely by industry)
- Display CTR: 0.1% average
- Conversion rate (lead gen): 3–6%
- Quality Score target: ≥7 on main keywords
