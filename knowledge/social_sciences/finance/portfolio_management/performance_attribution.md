# Performance Attribution

Decompose portfolio return into sources of alpha and beta.

## Brinson Attribution (single period)
```
Total excess return = Allocation + Selection + Interaction
Allocation = Σ (w_p,i - w_b,i) × R_b,i
Selection  = Σ w_b,i × (R_p,i - R_b,i)
Interaction = Σ (w_p,i - w_b,i) × (R_p,i - R_b,i)
```
- w_p: portfolio weight, w_b: benchmark weight
- R_p: portfolio return, R_b: benchmark return

## Factor Attribution
```
R_p = α + β₁F₁ + β₂F₂ + ... + ε
```
Common factors: Market, Size (SMB), Value (HML), Momentum (UMD), Quality.
Fama-French 5-factor model adds Profitability (RMW) and Investment (CMA).

## Information Ratio
```
IR = α / σ(α) = (R_p - R_b) / Tracking Error
```
- IR > 0.5: good | IR > 1.0: exceptional
- Tracking Error = std dev of active returns

## Key Metrics
- Alpha: return above risk-adjusted benchmark
- Beta: sensitivity to market
- R²: % of return explained by factors
- Maximum Drawdown: largest peak-to-trough decline
- Calmar Ratio: annualized return / max drawdown
