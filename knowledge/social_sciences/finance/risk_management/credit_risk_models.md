# Credit Risk Models

Quantifying probability and magnitude of borrower default.

## Key Metrics
```
Expected Loss = PD × LGD × EAD
```
- PD: Probability of Default (annual, from ratings or models)
- LGD: Loss Given Default (typically 40-60% for senior unsecured)
- EAD: Exposure at Default

## Altman Z-Score (Manufacturing)
```
Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5
```
- X1: Working Capital / Total Assets
- X2: Retained Earnings / Total Assets
- X3: EBIT / Total Assets
- X4: Market Value Equity / Book Value Debt
- X5: Sales / Total Assets
- Z > 2.99: Safe | 1.81-2.99: Grey | < 1.81: Distress

## Merton Model (Structural)
Firm defaults when asset value falls below debt at maturity.
```
PD = N(-d2)
d2 = [ln(V/D) + (r - σ²/2)×T] / (σ×√T)
```
- V: firm asset value, D: face value of debt
- σ: asset volatility, T: time to maturity
- Equity = Call option on firm assets (Black-Scholes)

## CreditMetrics (Portfolio)
1. Assign credit rating to each obligor
2. Define transition matrix (upgrade/downgrade/default probabilities)
3. Correlate defaults using asset correlation model
4. Simulate portfolio losses via Monte Carlo
5. Calculate portfolio VaR/ES

## Basel IRB Approach
```
K = LGD × N[(1-R)^(-0.5) × G(PD) + (R/(1-R))^0.5 × G(0.999)] - PD × LGD
```
- R: asset correlation (0.12-0.24 depending on PD)
- G(): inverse normal CDF
- N(): normal CDF
- Capital = K × EAD × 1.06 (scaling factor)

## Constraints
- Z-Score: only manufacturing, not financial firms
- Merton: assumes single debt maturity, lognormal assets
- CreditMetrics: transition matrices are historical averages
