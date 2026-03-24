# Attribution Models

## Single-Touch Models

### Last Click
```
100% credit → last touchpoint before conversion
```
- Simple, easy to implement
- Bias: overvalues bottom-funnel channels (branded search, retargeting)
- Undervalues awareness channels (display, social, content)

### First Click
```
100% credit → first touchpoint in journey
```
- Values channels that initiate discovery
- Ignores all nurturing touchpoints
- Use case: measuring brand awareness channel effectiveness

## Multi-Touch Models

### Linear
```
Equal credit distributed across all touchpoints
Journey: SEO → Email → Social → Paid → Convert
Credit:  25%    25%     25%    25%
```
- No touchpoint is more important than others (rarely true)

### Time Decay
```
More recent touchpoints get exponentially more credit
Half-life: typically 7 days (configurable)
```
- Rationale: recent interactions more influential on purchase decision
- Best for: short sales cycles, promotional campaigns

### Position-Based (U-Shaped)
```
First touch:   40% credit
Last touch:    40% credit
Middle touches: 20% credit (distributed equally)
```
- Values both acquisition and conversion touchpoints
- Ignores middle-funnel nurturing
- Most common model for B2B lead generation

### W-Shaped (B2B)
```
First touch:    30%
Lead creation:  30%
Opportunity:    30%
Middle touches: 10%
```
- Tracks key CRM milestones in B2B funnel

## Algorithmic / Data-Driven Attribution
```
Google's model: machine learning assigns fractional credit based on
  which touchpoints statistically correlate with conversion
  (requires minimum 400 conversions/month in GA4)
```
- Most accurate in theory; requires large data volume
- Black box: difficult to explain to stakeholders
- Available in: GA4, Google Ads, some CDPs

## Attribution Challenges

### Multi-Touch Attribution Limitations
- Cross-device: same user on mobile + desktop = two users in most tools
- Cross-browser: cookie deletion, iOS privacy changes (ATT)
- Offline touchpoints (events, sales calls) not tracked
- View-through vs. click-through controversy
- Walled gardens: Meta, TikTok, Google don't share raw impression data

### Marketing Mix Modeling (MMM) vs. Multi-Touch
| Aspect | MMM | Multi-Touch |
|--------|-----|-------------|
| Data type | Aggregate (no user-level) | User-level journeys |
| Privacy | No cookies/IDs needed | Requires tracking |
| Granularity | Channel/weekly level | Individual touchpoints |
| Latency | Months to build | Real-time |
| Best for | Long-term budget allocation | Day-to-day optimization |

## Practical Recommendation
- Small budgets (<$50K/month): use last-click + sanity check with first-click
- Mid-market: position-based (U-shaped) for balance
- Enterprise: data-driven + MMM for budget planning
- Always supplement with: incrementality testing, geo holdout experiments
