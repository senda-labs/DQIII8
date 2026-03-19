# DCF — Methodology

## Concept

DCF (Discounted Cash Flow) values a company as the present value
of its future free cash flows discounted at the WACC.

EV = Σ [FCFt / (1 + WACC)^t] + TV / (1 + WACC)^n

## Free Cash Flow (FCF)

FCF = EBIT × (1 − t) + D&A − CAPEX − ΔNWC

Where:
- EBIT × (1 − t) = NOPAT (net operating profit after tax)
- D&A = depreciation and amortization (non-cash, added back)
- CAPEX = capital expenditure (cash outflow)
- ΔNWC = change in net working capital

### Net Working Capital (NWC)

NWC = (Receivables + Inventory) − Payables
ΔNWC positive = more capital tied up → reduces FCF

## Terminal Value (Gordon Growth)

TV = FCFn × (1 + g) / (WACC − g)

- g = perpetual growth rate (typical: 1.5–2.5% in developed markets)
- g must be ≤ nominal GDP growth of the sector
- Rule: TV typically represents 60–80% of total EV → highly sensitive

### Alternative: Exit Multiple

TV = EBITDAn × sector_multiple

Useful for cross-validation with the Gordon method.

## From EV to Equity Value

Equity Value = EV − Net Debt + Non-Operating Assets

Net Debt = Gross financial debt − Cash and equivalents

## Horizon and Phases

Phase 1 (years 1–5): explicit P&L + FCF projection
Phase 2 (years 6–10, optional): growth converging toward g
Phase 3: terminal value

For growth companies: use 2 phases with higher WACC in phase 1.

## Sensitivity Analysis

Mandatory 2D table in any professional DCF:

|        | g=1.0% | g=1.5% | g=2.0% | g=2.5% |
|--------|--------|--------|--------|--------|
| W=6.0% |        |        |        |        |
| W=6.5% |        |   BASE |        |        |
| W=7.0% |        |        |        |        |
| W=7.5% |        |        |        |        |

Practical rule:
- +1% WACC → −15 to −25% in EV
- +0.5% g → +10 to +15% in EV

## Model Limitations

1. Extreme sensitivity to g and WACC (small changes → large impact)
2. FCF projections > 5Y have high uncertainty
3. Ignores real options (expansion, divestiture)
4. For cyclical companies: use normalized FCF, not spot FCF
5. Maintenance vs. growth CAPEX should be separated
6. Negative FCF in early years is valid (growth companies)

## Cross-Validation

Always cross-check DCF with multiples valuation:
- If DCF implies EV/EBITDA >> peers → revisit g or margin assumptions
- Tolerable difference DCF vs. multiples: ±20%
- Difference > 30% → identify and justify the main driver
