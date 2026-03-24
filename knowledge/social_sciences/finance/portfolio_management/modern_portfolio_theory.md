# Modern Portfolio Theory (MPT)

Optimal portfolio maximizes return for given risk via diversification.

## Portfolio Return
```
E(R_p) = Σ w_i × E(R_i)
```

## Portfolio Variance (2 assets)
```
σ²_p = w₁²σ₁² + w₂²σ₂² + 2×w₁×w₂×ρ₁₂×σ₁×σ₂
```
For N assets:
```
σ²_p = Σ Σ w_i × w_j × σ_ij
```

## Efficient Frontier
Set of portfolios offering highest return per unit risk.
Computed via quadratic optimization: min σ²_p subject to E(R_p) = target.

## Capital Market Line (CML)
```
E(R_p) = R_f + [(E(R_m) - R_f) / σ_m] × σ_p
```
Slope = Sharpe ratio of market portfolio.

## CAPM
```
E(R_i) = R_f + β_i × [E(R_m) - R_f]
```
- β_i = Cov(R_i, R_m) / Var(R_m)
- β > 1: more volatile than market
- β < 1: less volatile than market

## Sharpe Ratio
```
S = (R_p - R_f) / σ_p
```
Higher = better risk-adjusted return. Benchmark: S > 1 is excellent.

## Sortino Ratio
```
Sortino = (R_p - R_f) / σ_downside
```
Only penalizes downside volatility. Better for asymmetric returns.

## Limitations of MPT
- Assumes normal returns (markets have fat tails)
- Correlation increases in crises (diversification fails when needed most)
- Sensitive to input estimates (garbage in = garbage out)
- Single-period model (no rebalancing dynamics)
