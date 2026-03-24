# Valuation Methods

## DCF (Discounted Cash Flow)
```
Value = Σ FCF_t / (1+r)^t + Terminal Value / (1+r)^n
Terminal Value = FCF_{n+1} / (r - g)  [Gordon Growth]
```
- r: WACC for FCFF, cost of equity for FCFE
- g: perpetual growth rate (typically 2-3%, ≤ GDP growth)
- Most sensitive to: discount rate and terminal growth

## WACC
```
WACC = (E/V)×R_e + (D/V)×R_d×(1-t)
```
- E: market cap, D: market value of debt, V = E+D
- R_e: cost of equity (from CAPM)
- R_d: cost of debt (yield on bonds)
- t: corporate tax rate

## Comparable Company Analysis (Comps)
1. Select peer group (same industry, size, growth)
2. Calculate multiples: EV/EBITDA, P/E, EV/Revenue
3. Apply median multiple to target's metric
4. Adjust for growth differential, margins, risk

## Precedent Transactions
Same as comps but using M&A transaction multiples.
Include control premium (typically 20-40%).

## LBO Valuation
```
Entry: EV = EBITDA × Entry Multiple
Debt: typically 4-6x EBITDA
Equity: EV - Debt
Exit: EV_exit = EBITDA_exit × Exit Multiple
IRR: (Equity_exit / Equity_entry)^(1/years) - 1
```
Target IRR: 20-25% for PE firms.

## When to use
- DCF: intrinsic value, stable cash flows, long-term view
- Comps: relative value, liquid markets, quick estimate
- Precedent: M&A pricing, control premium
- LBO: PE, leveraged transactions
