# Value at Risk (VaR) Methods

Maximum potential loss at a confidence level over a time horizon.

## Parametric (Variance-Covariance)
```
VaR_α = Z_α × σ_p × √t × V
```
- Z_α: 1.645 (95%), 2.326 (99%)
- σ_p: portfolio daily standard deviation
- t: holding period (days)
- V: portfolio value
- Assumes normal returns. Fails for fat tails, options, skewed distributions.

## Historical Simulation
1. Collect 250-500 days historical returns
2. Apply each return to current portfolio
3. Sort P&L worst to best
4. VaR = (1-α)×N th worst loss

No distribution assumption. Limited by data quality and regime changes.

## Monte Carlo
1. Define stochastic process per risk factor (GBM, Heston, etc.)
2. Generate 10,000+ scenarios
3. Revalue portfolio per scenario
4. VaR = percentile of simulated P&L

Most flexible. Handles non-linear instruments. Computationally expensive.

## Expected Shortfall (CVaR)
```
ES_α = E[Loss | Loss > VaR_α]
```
Average of all losses beyond VaR. Always ≥ VaR.
Coherent risk measure (satisfies subadditivity).

## Regulatory Context (Basel IV / FRTB)
- FRTB replaced 99% VaR with 97.5% Expected Shortfall
- For normal distribution: 99% VaR ≈ 97.5% ES (Z=2.326 vs Z=2.338)
- For fat-tailed distributions: 97.5% ES >> 99% VaR
- Base horizon: 10 days, calculated directly (not scaled from 1-day)
- Stressed period: 250-day window of market stress (bank selects)
- 5 liquidity horizons: 10, 20, 40, 60, 120 days by asset class
- Market risk capital increase under FRTB: ~63% for G-SIBs

## When to use
- Parametric: quick estimate, linear portfolios, normal markets
- Historical: no assumptions, sufficient data, regime-stable
- Monte Carlo: options, structured products, stress testing
- ES: regulatory reporting (Basel IV), tail risk management
