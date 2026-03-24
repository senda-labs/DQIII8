# Asset Allocation Strategies

How to distribute capital across asset classes.

## Strategic Asset Allocation (SAA)
Long-term target based on risk tolerance and investment horizon.
Typical allocations:
- Conservative: 30/60/10 (equity/bonds/alternatives)
- Balanced: 60/30/10
- Aggressive: 80/10/10
Rebalance quarterly/annually to targets.

## Tactical Asset Allocation (TAA)
Short-term deviations from SAA based on market views.
Typical range: ±5-10% from strategic weights.
Risk: market timing is difficult. Most TAA underperforms SAA.

## Risk Parity
Weight by inverse volatility so each asset contributes equal risk.
```
w_i ∝ 1/σ_i (simplified)
RC_i = w_i × (Σ × w)_i / σ_p (exact risk contribution)
```
Target: RC_i = RC_j for all i,j.
Typically: more bonds, less equity than traditional 60/40.

## Black-Litterman Model
Combines market equilibrium with investor views.
```
E(R) = [(τΣ)^(-1) + P'Ω^(-1)P]^(-1) × [(τΣ)^(-1)π + P'Ω^(-1)Q]
```
- π: implied equilibrium returns
- P: view matrix, Q: view returns, Ω: view uncertainty
- τ: scalar (0.01-0.05)

## Factor-Based Allocation
Allocate to risk factors not asset classes:
- Equity risk premium, term premium, credit spread, inflation, momentum
- More stable diversification than asset-class allocation

## Rebalancing Methods
- Calendar: fixed schedule (monthly, quarterly)
- Threshold: rebalance when weight deviates >5% from target
- Cost-aware: only rebalance if benefit > transaction cost
