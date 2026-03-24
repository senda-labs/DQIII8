# WACC — Fundamentals

## General Formula

WACC = Ke × (E/V) + Kd × (1 − t) × (D/V)

Where:
- Ke = cost of equity (shareholders)
- Kd = cost of debt (pre-tax)
- E = market value of equity
- D = market value of net financial debt
- V = E + D (total enterprise value)
- t = effective tax rate

## Cost of Equity — CAPM

Ke = Rf + β × Pm

- Rf = risk-free rate (10Y sovereign bond)
- β = asset beta (market sensitivity)
- Pm = equity risk premium (ERP)

### Levered vs. Unlevered Beta

β_L = β_U × [1 + (D/E) × (1 − t)]

- β_U = unlevered beta (sector comparable, without financial leverage effect)
- β_L = levered beta (reflects the company's capital structure)

## International Reference Parameters (2026)

Use the appropriate parameters for the target market:

- Rf: 10Y sovereign bond of the relevant country (e.g. 3.0–4.5% for developed markets)
- ERP (Damodaran): typically 5.0–7.0% depending on country risk
- Sectoral beta (industrials): 0.80–1.10 (vary by sector and market cycle)
- Corporate tax rate: country-specific (common range: 20–30%)

> Sources: Damodaran Online (annual update), Bloomberg, Reuters

## Cost of Debt

Kd = weighted average interest rate on financial debt

Sources in order of preference:
1. Financial interest / average financial debt (P&L / balance sheet)
2. Credit rating → spread over swap rate
3. Proxy: reference interbank rate + sector spread

After-tax cost of debt = Kd × (1 − t)

## Numerical Example — Generic Industrial Company

Data:
- Equity: 800 M, Net debt: 400 M → V = 1,200 M
- Rf = 3.2%, β_L = 0.95, ERP = 6.0%
- Kd = 4.5%, t = 23%

Calculation:
- Ke = 3.2% + 0.95 × 6.0% = 8.9%
- After-tax Kd = 4.5% × (1 − 0.23) = 3.5%
- Weights: E/V = 67%, D/V = 33%
- WACC = 8.9% × 0.67 + 3.5% × 0.33 = **7.1%**

## Regulatory / Valuation Advisory Considerations

- Valuation reports for M&A and public offerings must justify Rf and ERP choices
- Beta: use 2Y weekly average or 5Y monthly (source: Bloomberg, Reuters)
- If the company is unlisted: use unlevered beta from listed peers + re-levering
- Regulators typically require sensitivity of final value to ±0.5% WACC in formal reports

## WACC Sensitivity

Practical rule: ±1% in WACC → ±15–25% in DCF valuation

Key drivers of WACC changes:
1. Beta (especially during the economic cycle)
2. Equity risk premium (annual Damodaran update)
3. Target D/E structure (if leverage changes)
