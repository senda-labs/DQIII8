# Greeks — Option Sensitivities

## Delta (Δ)
```
Δ = ∂V/∂S = N(d1) for calls, N(d1)-1 for puts
```
- Range: 0 to 1 (calls), -1 to 0 (puts)
- ATM ≈ 0.50, deep ITM ≈ 1.0, deep OTM ≈ 0

## Gamma (Γ)
```
Γ = ∂²V/∂S² = N'(d1) / (S×σ×√T)
```
- Rate of change of delta. Highest ATM near expiry.
- Long gamma = profits from large moves (straddle).
- Short gamma = risk from large moves (selling options).

## Theta (Θ)
```
Θ = ∂V/∂t ≈ -(S×N'(d1)×σ)/(2√T) - r×K×e^(-rT)×N(d2)
```
Time decay. Usually negative (options lose value daily).
ATM options decay fastest near expiry.

## Vega (ν)
```
ν = ∂V/∂σ = S×√T×N'(d1)
```
Sensitivity to implied vol. Highest ATM, longer-dated options.
Long vega = profits from vol increase. Short vega = profits from vol decrease.

## Rho (ρ)
```
ρ = ∂V/∂r = K×T×e^(-rT)×N(d2) for calls
```
Sensitivity to interest rates. Small effect except for long-dated options.

## Portfolio Greeks
```
Portfolio Delta = Σ Δ_i × position_i
Portfolio Gamma = Σ Γ_i × position_i
```
Delta-neutral: portfolio Δ = 0 (hedged against small moves).
Gamma-neutral: portfolio Γ = 0 (hedged against large moves).
