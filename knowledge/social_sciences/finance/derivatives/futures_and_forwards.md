# Futures and Forwards

## Forward Price (no income)
```
F = S × e^(rT)
```

## Forward Price (continuous dividend yield q)
```
F = S × e^((r-q)T)
```

## Forward Price (storage cost u, convenience yield y)
```
F = S × e^((r+u-y)T)
```

## Cost of Carry
```
F = S × e^(cT)  where c = r + u - q - y
```
- r: risk-free rate, u: storage cost
- q: dividend yield, y: convenience yield

## Basis and Convergence
```
Basis = Spot - Futures
```
At expiry: basis → 0 (convergence). Before expiry: basis can be positive (backwardation) or negative (contango).

## Futures vs Forwards
- Futures: exchange-traded, standardized, daily settlement (margin)
- Forwards: OTC, customizable, settlement at expiry
- Credit risk: futures have clearinghouse guarantee; forwards have counterparty risk

## Hedging with Futures
```
Optimal contracts = h* × (Q_exposure / Q_contract)
h* = ρ(ΔS,ΔF) × σ(ΔS) / σ(ΔF)
```

## Mark-to-Market (Daily Settlement)
Daily P&L = (F_today - F_yesterday) × contract_size × num_contracts
Margin call if balance < maintenance margin.
