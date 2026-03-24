# Factor Models in Finance

## CAPM (Single Factor)
```
E(R_i) = R_f + β_i × [E(R_m) - R_f]
```
Single factor: market risk premium. β = systematic risk.

## Fama-French 3-Factor
```
R_i - R_f = α + β₁(R_m - R_f) + β₂×SMB + β₃×HML + ε
```
- SMB: Small Minus Big (size premium)
- HML: High Minus Low (value premium)

## Fama-French 5-Factor (2015)
```
R_i - R_f = α + β₁(R_m-R_f) + β₂×SMB + β₃×HML + β₄×RMW + β₅×CMA + ε
```
- RMW: Robust Minus Weak (profitability)
- CMA: Conservative Minus Aggressive (investment)

## Carhart 4-Factor
```
= FF3 + β₄×UMD
```
- UMD: Up Minus Down (12-1 month momentum)

## APT (Arbitrage Pricing Theory)
```
E(R_i) = R_f + Σ β_ij × λ_j
```
- λ_j: risk premium for factor j
- Factors: macro (GDP, inflation, rates) or statistical (PCA)

## Risk Factor Premia (Historical averages, US)
- Equity premium: ~5-7% annually
- Size (SMB): ~2-3% annually
- Value (HML): ~3-5% annually (weakened post-2010)
- Momentum: ~6-8% annually (with crashes)
- Quality: ~3-4% annually

## Practical Application
1. Run regression of portfolio returns on factor returns
2. α > 0: manager adds value beyond factor exposure
3. R²: how much return is explained by factors
4. Use for: performance attribution, risk decomposition, portfolio construction
