# Time Series Analysis for Finance

## Returns
```
Simple return: R_t = (P_t - P_{t-1}) / P_{t-1}
Log return: r_t = ln(P_t / P_{t-1})
```
Log returns are additive over time. Simple returns are not.

## GARCH(1,1) — Volatility Modeling
```
σ²_t = ω + α×ε²_{t-1} + β×σ²_{t-1}
```
- ω: long-run variance weight
- α: reaction to shocks (typically 0.05-0.15)
- β: persistence (typically 0.85-0.95)
- α + β < 1 for stationarity
- Long-run variance = ω / (1 - α - β)

## EWMA (RiskMetrics)
```
σ²_t = λ×σ²_{t-1} + (1-λ)×r²_{t-1}
```
- λ = 0.94 (daily, RiskMetrics standard)
- λ = 0.97 (monthly)
- No mean reversion (GARCH special case where ω = 0)

## Stationarity Tests
- ADF (Augmented Dickey-Fuller): H0 = unit root (non-stationary)
- KPSS: H0 = stationary (opposite null)
- Rule: if ADF rejects AND KPSS doesn't reject → stationary

## Cointegration
Two non-stationary series that move together long-term.
```
y_t = α + β×x_t + ε_t  where ε_t is stationary
```
- Test: Engle-Granger (2-step), Johansen (multi-variable)
- Application: pairs trading, spread trading

## Practical Notes
- Financial returns are NOT normally distributed (fat tails, skew)
- Volatility clusters (high vol follows high vol)
- Use log returns for modeling, simple returns for reporting
- Always check for stationarity before modeling
