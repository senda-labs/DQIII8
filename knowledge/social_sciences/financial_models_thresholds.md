---
domain: social_sciences
agent: finance-specialist
keywords_es: [VaR, Basel, WACC, DCF, Sharpe, ratio, riesgo, valoración, CAPM, Black-Scholes, capital, CET1, Expected Shortfall, Altman Z-score]
keywords_en: [VaR, Basel, WACC, DCF, Sharpe, ratio, risk, valuation, CAPM, Black-Scholes, capital, CET1, Expected Shortfall, Altman Z-score]
---

# Financial Models — Thresholds & Exact Parameters

## Basel IV Capital Requirements (fully phased in 2028)

| Buffer | Requirement | Notes |
|--------|-------------|-------|
| CET1 minimum | 4.5% | Common Equity Tier 1 |
| Tier 1 minimum | 6.0% | CET1 + Additional T1 |
| Total Capital minimum | 8.0% | T1 + Tier 2 |
| Capital Conservation Buffer | +2.5% | must be CET1 |
| Countercyclical Buffer (CCyB) | 0–2.5% | set by national authority |
| G-SIB surcharge | 1.0–3.5% | bucket 1–5 (HSBC, JPM: 2.5–3.5%) |
| **Effective CET1 (large banks)** | **10–13%** | incl. conservation + CCyB + G-SIB |

Basel IV vs Basel III key change: Expected Shortfall replaces VaR for market risk (FRTB).

## Risk Measures

### Value at Risk (VaR)

```
Parametric (normal): VaR_alpha = mu + z_alpha * sigma
  z at 95% = 1.645; z at 99% = 2.326; z at 99.9% = 3.090

Historical simulation: sort 250 daily P&L, take (1-alpha) percentile
Monte Carlo: simulate 10k+ scenarios, take (1-alpha) percentile
```

### Expected Shortfall / CVaR (Basel IV mandatory)

```
ES_alpha = -E[X | X <= VaR_alpha]
Parametric (normal): ES_alpha = mu - sigma * phi(z_alpha)/(1-alpha)
  phi = standard normal PDF

At 97.5%: ES ≈ 2.06 * daily_sigma (vs VaR_99% ≈ 2.33 * sigma)
```

FRTB liquid horizons: 10d (IG bonds, FX majors), 20d (IG CDS), 40d (HY bonds), 60d (IG equity), 120d (exotics)

## CAPM & WACC

```
Re = Rf + beta * ERP
  Rf (US, 2025): ~4.3% (10Y Treasury)
  ERP Damodaran Jan 2025: US = 4.60%, W. Europe = 5.85%, Emerging = 7.5%
  beta: unlevered beta re-levered = beta_u * (1 + (1-t)*D/E)

WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)
  Tc (US federal): 21%; effective: ~25-27% with state taxes
  Rd = pre-tax cost of debt (yield to maturity)
  E/V, D/V = market value weights (NOT book value)
```

## Black-Scholes Option Pricing

```
C = S0*N(d1) - K*e^(-rT)*N(d2)
P = K*e^(-rT)*N(-d2) - S0*N(-d1)   [put-call parity check]

d1 = [ln(S0/K) + (r + sigma²/2)*T] / (sigma*sqrt(T))
d2 = d1 - sigma*sqrt(T)

Put-call parity: C - P = S0 - K*e^(-rT)
```

### Option Greeks

| Greek | Formula | Interpretation |
|-------|---------|----------------|
| Delta (Δ) | N(d1) for call; N(d1)-1 for put | dC/dS; hedge ratio |
| Gamma (Γ) | phi(d1)/(S*sigma*sqrt(T)) | d²C/dS²; delta sensitivity |
| Theta (Θ) | −[S*phi(d1)*sigma/(2sqrt(T))] − rK*e^(-rT)*N(d2) | dC/dt (per year, usually negative) |
| Vega (V) | S*phi(d1)*sqrt(T) | dC/d(sigma); per 1% move in vol |
| Rho (ρ) | K*T*e^(-rT)*N(d2) | dC/dr; per 1% move in rate |

## Altman Z-Score

```
Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

X1 = Working Capital / Total Assets
X2 = Retained Earnings / Total Assets
X3 = EBIT / Total Assets
X4 = Market Cap / Book Value of Total Liabilities
X5 = Revenue / Total Assets

Thresholds (public manufacturing):
  Z < 1.81  → Distress Zone (high default probability)
  1.81–2.99 → Grey Zone
  Z > 2.99  → Safe Zone

Z' model (private firms): X4 = Book Equity / Total Liabilities; thresholds 1.23/2.90
Z'' model (non-manufacturing): no X5; thresholds 1.10/2.60
```

## Performance Ratios

| Ratio | Formula | Interpretation | Benchmark |
|-------|---------|----------------|-----------|
| Sharpe | (Rp - Rf) / sigma_p | risk-adjusted return (total vol) | >1 good, >2 excellent |
| Sortino | (Rp - Rf) / sigma_d | downside deviation only | >2 good |
| Treynor | (Rp - Rf) / beta | systematic risk only | compare across portfolios |
| Information | (Rp - Rb) / tracking_error | active return per unit active risk | >0.5 good |
| Calmar | CAGR / max_drawdown | return per unit worst drawdown | >1 acceptable |
| MAR | CAGR / max_drawdown | same as Calmar | >1 |
| Omega | P(R>threshold) / P(R<threshold) | all moments | >1 |

## DCF Terminal Value Methods

```
Gordon Growth: TV = FCF_{T+1} / (WACC - g)
  g must be < nominal GDP growth long-term (~2-3%)

Exit Multiple: TV = EBITDA_T * EV/EBITDA_comparable
  Use sector median multiples; sensitivity table required

Terminal value typically = 60-80% of enterprise value in DCF
→ implies model is highly sensitive to WACC and g assumptions
```

**Source:** BIS Basel III/IV framework (bis.org/bcbs) + Damodaran Online (pages.stern.nyu.edu/~adamodar) + Hull "Options, Futures & Other Derivatives" 11th ed.
