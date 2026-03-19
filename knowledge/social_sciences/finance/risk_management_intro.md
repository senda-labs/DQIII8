# Risk Management — Introduction
**Domain:** Social Sciences / Finance
**Tier:** FREE — included in community edition

## What is VaR

Value at Risk (VaR) is a statistical measure that estimates the maximum potential loss
of a portfolio over a given time period, at a given confidence level.

Example: "VaR 95% at 1 day = $10,000" means there is a 5% chance of losing more than
$10,000 in a single trading day.

VaR is expressed in three dimensions:
- **Confidence level** — typically 95% or 99%
- **Time horizon** — 1 day, 10 days, 1 year
- **Loss amount** — the estimated maximum loss

## The Three Main Methods

### Historical Simulation
Uses actual past returns to simulate what the current portfolio would have earned
(or lost) in historical periods. Simple to explain, no distributional assumptions.

### Parametric (Variance-Covariance)
Assumes returns follow a normal distribution. Uses portfolio mean and standard deviation
to calculate VaR analytically. Fast and mathematically clean, but sensitive to
distributional assumptions.

### Monte Carlo Simulation
Generates thousands of random scenarios based on statistical properties of the assets.
Most flexible method — can incorporate complex dependencies and non-normal distributions.
Computationally intensive.

## When to Use Each Method

| Situation | Recommended method |
|-----------|-------------------|
| Simple portfolio, few assets | Historical or Parametric |
| Regulatory reporting (Basel) | Historical (minimum 250 days) |
| Options or non-linear exposures | Monte Carlo |
| Fast real-time estimates | Parametric |
| Fat tail concerns | Historical or Monte Carlo |

## Known Limitations of VaR

- Does not describe the severity of losses beyond the threshold (tail risk)
- Assumes historical patterns repeat — fails in regime changes
- Can be manipulated by changing confidence level or time horizon
- Does not capture liquidity risk
- Correlations change during crisis periods (diversification breaks down)

## Complementary Measures

- **Expected Shortfall (CVaR)** — average loss beyond VaR threshold; better tail metric
- **Stress Testing** — scenario-based losses under extreme but plausible events
- **Drawdown analysis** — peak-to-trough loss over a period

## Context

VaR is a standard tool in financial risk management, required by Basel III/IV for
bank capital requirements. It is widely used in portfolio management, trading desks,
and regulatory reporting — but should never be used as the sole risk metric.
