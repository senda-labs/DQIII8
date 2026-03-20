# Marketing KPI Framework

## Customer Acquisition

### CAC (Customer Acquisition Cost)
```
CAC = Total marketing & sales spend / New customers acquired
      (in same period)
```
- Include: ad spend, salaries (marketing + sales), tools, agency fees
- CAC by channel: isolate spend per channel to identify efficiency

### Payback Period
```
Payback = CAC / (ARPU × gross margin)
```
- Target: <12 months for SaaS, <6 months for high-growth
- Long payback requires more capital (cash flow risk)

## Customer Value

### LTV (Lifetime Value)
```
LTV = ARPU × gross margin % × average customer lifespan
    = ARPU × margin / churn rate  (for subscription businesses)
```
- ARPU: Average Revenue Per User
- Lifespan = 1 / monthly churn rate (if churn = 2%, lifespan = 50 months)

### LTV:CAC Ratio
```
Healthy:   >3:1
Excellent: >5:1
Concern:   <2:1 (acquiring customers too expensively)
```
Benchmark: SaaS industry target is 3:1 minimum.

## Retention Metrics

### Churn Rate
```
Monthly churn = Lost customers in period / Customers at start of period
Annual churn  = 1 - (1 - monthly churn)^12
```
- SaaS benchmarks: <2% monthly (B2C), <1% monthly (B2B enterprise)
- Net Revenue Retention (NRR) = (Starting MRR + Expansion - Contraction - Churn) / Starting MRR
  - NRR >100% = growth even without new customers (expansion revenue)

## Revenue Metrics (SaaS)

### MRR / ARR
```
MRR = Σ monthly recurring revenue from all active subscriptions
ARR = MRR × 12

MRR growth rate = (MRR_end - MRR_start) / MRR_start
```
- MRR movements: New MRR, Expansion MRR, Contraction MRR, Churned MRR, Reactivation MRR

### Rule of 40 (SaaS health)
```
Revenue growth % + EBITDA margin % ≥ 40
```
- Company growing 50% YoY with -10% margin = 40 (passing)
- Profitable company at 5% growth needs 35% EBITDA margin

## Conversion Funnel Metrics
```
Visitor → Lead: conversion rate 1–5% (B2B website average)
Lead → MQL:    depends on lead scoring threshold
MQL → SQL:     20–30% (qualified by sales)
SQL → Customer: 20–30% (close rate)

Full funnel: 1,000 visitors → 30 leads → 8 MQLs → 2 SQLs → 0.5 customers
```

## Reporting Cadence
- Daily: spend, ROAS, CPA (paid channels)
- Weekly: leads, pipeline, channel performance
- Monthly: CAC, LTV, churn, MRR movements
- Quarterly: LTV:CAC, payback period, cohort analysis
