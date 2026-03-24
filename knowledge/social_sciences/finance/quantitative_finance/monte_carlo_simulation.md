# Monte Carlo Simulation in Finance

## Geometric Brownian Motion (GBM)
```
S_t = S_0 × exp[(μ - σ²/2)t + σ×W_t]
```
Discrete step:
```
S_{t+Δt} = S_t × exp[(μ - σ²/2)Δt + σ×ε×√Δt]
```
- μ: drift (expected return), σ: volatility
- ε ~ N(0,1): standard normal random variable
- W_t: Wiener process (Brownian motion)

## Risk-Neutral Pricing
Replace μ with r (risk-free rate) for derivative pricing:
```
S_{t+Δt} = S_t × exp[(r - σ²/2)Δt + σ×ε×√Δt]
```
Option price = e^(-rT) × mean(payoffs across all paths)

## Correlated Assets
Use Cholesky decomposition:
```
ε_correlated = L × ε_independent
```
Where L×L' = correlation matrix Σ.

## Variance Reduction
- Antithetic variates: for each ε, also simulate -ε
- Control variates: use known-price instrument to reduce error
- Importance sampling: sample more from critical regions

## Convergence
```
Standard error = σ_payoff / √N
```
10,000 paths: ~1% precision. 1,000,000 paths: ~0.1% precision.
Doubling precision requires 4x paths.

## Applications
- Option pricing (especially path-dependent: Asian, barrier, lookback)
- VaR/ES calculation
- Credit portfolio loss simulation
- Real options analysis
- Retirement planning / ALM
