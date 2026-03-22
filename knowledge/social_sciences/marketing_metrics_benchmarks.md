---
domain: social_sciences
agent: marketing-specialist
keywords_es: [SEO, conversión, CTR, CAC, LTV, embudo, ROI, analítica, email, Google Ads, redes sociales, tasa rebote, Core Web Vitals, ROAS]
keywords_en: [SEO, conversion, CTR, CAC, LTV, funnel, ROI, analytics, email, Google Ads, social media, bounce rate, Core Web Vitals, ROAS]
---

# Marketing Metrics & Benchmarks Reference

## Paid Advertising CTR Benchmarks

### Google Ads (2024–2025, cross-industry average)

| Network | Avg CTR | Avg CVR | Avg CPC |
|---------|---------|---------|---------|
| Search | 3.17% | 3.75% | $4.22 |
| Display | 0.46% | 0.77% | $0.63 |
| Shopping | 0.86% | 1.91% | $0.66 |

### CPC by Industry (Google Search, 2024)

| Industry | Avg CPC | Avg CVR |
|----------|---------|---------|
| Insurance | $54.91 | 1.19% |
| Legal | $47.07 | 3.84% |
| Dental | $6.69 | 3.70% |
| Real Estate | $2.37 | 2.47% |
| B2B Software | $3.80 | 2.23% |
| E-commerce | $1.16 | 2.69% |
| Finance & Banking | $12.53 | 4.00% |
| Healthcare | $8.39 | 3.36% |
| Travel & Hospitality | $1.63 | 3.55% |

### Social Media CTR

| Platform | Avg CTR | Avg CPM | Avg CPC |
|----------|---------|---------|---------|
| Facebook Feed | 0.90% | $14.40 | $1.72 |
| Instagram Feed | 0.22% | $10.11 | $3.56 |
| Instagram Stories | 0.33% | $7.91 | $2.26 |
| LinkedIn | 0.26% | $33.80 | $5.26 |
| Twitter/X | 0.46% | $6.46 | $0.38 |
| TikTok | 0.84% | $9.16 | $1.00 |
| Pinterest | 0.30% | $1.50 | $1.50 |
| YouTube TrueView | 0.51% | $9.68 | view-based |

## Email Marketing Benchmarks (2024, Mailchimp/Campaign Monitor)

| Metric | Average | Top Quartile |
|--------|---------|-------------|
| Open rate (all industries) | 21.33% | 35%+ |
| Click-through rate | 2.62% | 5%+ |
| Click-to-open rate (CTOR) | 14.10% | — |
| Unsubscribe rate | 0.26% | <0.1% |
| Bounce rate (hard) | 0.40% | <0.1% |
| Spam complaint rate | 0.02% | <0.01% |

Best send times: Tue/Thu 10am or 2pm (user local time)
Worst: Monday morning, Friday afternoon, weekends
Subject line optimal length: 41–50 characters (mobile preview ~30 chars)

## Conversion Rate Benchmarks by Sector

| Sector | Average CVR | Top 25% CVR |
|--------|------------|-------------|
| E-commerce (general) | 2.5–3.0% | 5%+ |
| SaaS free trial → paid | 15–25% | 30%+ |
| SaaS website → trial | 2–5% | 8%+ |
| B2B lead generation | 2.23% | 5%+ |
| Travel booking | 2.0% | 4%+ |
| Finance/insurance | 5.0% | 9%+ |
| Healthcare | 3.36% | 6%+ |
| Real estate lead | 2.47% | 5%+ |

## Customer Economics

```
CAC = Total Marketing & Sales Spend / New Customers Acquired
LTV = ARPU × Gross Margin % × Average Customer Lifetime

Healthy LTV:CAC ratio: >= 3:1
Payback period: CAC / (ARPU × Gross Margin %) < 12 months (SaaS)
Quick ratio (SaaS): (New MRR + Expansion MRR) / (Churned MRR + Contracted MRR) >= 4

ROAS = Revenue from Ads / Ad Spend (minimum 200-400% = 2x-4x)
  Breakeven ROAS = 1 / Gross Margin %
  E.g. 40% margin → breakeven ROAS = 2.5x
```

## SEO — Core Web Vitals Thresholds (2024)

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| LCP (Largest Contentful Paint) | <= 2.5s | 2.5–4.0s | > 4.0s |
| INP (Interaction to Next Paint) | <= 200ms | 200–500ms | > 500ms |
| CLS (Cumulative Layout Shift) | <= 0.1 | 0.1–0.25 | > 0.25 |
| TTFB (Time to First Byte) | <= 800ms | 800ms–1.8s | > 1.8s |
| FCP (First Contentful Paint) | <= 1.8s | 1.8–3.0s | > 3.0s |

**INP replaced FID (First Input Delay) in March 2024 — old benchmarks (<100ms) are obsolete.**

## GA4 Standard Events (Automatic & Enhanced Measurement)

| Event | Trigger | Key Parameters |
|-------|---------|----------------|
| page_view | every page load | page_location, page_title |
| scroll | 90% vertical scroll | percent_scrolled |
| click | outbound clicks | link_url, link_text |
| view_search_results | on-site search | search_term |
| file_download | file link click | file_name, file_extension |
| form_start | first form interaction | form_id, form_name |
| form_submit | form submission | form_id |
| video_start/progress/complete | YouTube embedded | video_title, video_percent |
| purchase | conversion | transaction_id, value, currency, items[] |
| add_to_cart | add item | items[], value |
| begin_checkout | checkout start | items[], value |
| generate_lead | lead form | value, currency |

Attribution models (GA4): Data-driven (default), Last click, First click, Linear, Time decay, Position-based

**Source:** WordStream Industry Benchmarks 2024 + Mailchimp Email Marketing Benchmarks 2024 + Google Web Vitals documentation (web.dev/vitals)
