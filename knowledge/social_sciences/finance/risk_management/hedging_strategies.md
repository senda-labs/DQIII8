# Hedging Strategies

Reducing exposure to specific risk factors using offsetting positions.

## Delta Hedging
```
Hedge ratio = -Δ (delta of option)
Position = -Δ × N × underlying
```
Rebalance as delta changes (dynamic hedging). Cost = gamma × (ΔS)² / 2.

## Minimum Variance Hedge Ratio
```
h* = ρ × (σ_S / σ_F)
```
- ρ: correlation between spot and futures
- σ_S: std dev of spot price changes
- σ_F: std dev of futures price changes
- Optimal # contracts: h* × (Q_A / Q_F)

## Cross-Hedging
When no direct futures contract exists for the asset.
Use correlated asset futures. Effectiveness depends on basis risk.
```
Basis = Spot price - Futures price
Basis risk = uncertainty in basis at hedge close
```

## Portfolio Insurance (Protective Put)
- Buy put on portfolio (or index proxy)
- Floor = Strike - Premium paid
- Cost: option premium (1-3% of portfolio value annually)

## VIX Hedging
- Long VIX calls/futures as tail risk hedge
- VIX typically rises 4-5x during market crashes
- Carry cost: VIX futures in contango (roll cost ~3-5%/month)

## Currency Hedging
- Forward contract: lock exchange rate, zero cost, gives up upside
- Options: pay premium, keep upside
- Natural hedge: match revenue/cost currencies
```
Forward rate = Spot × (1 + r_domestic)/(1 + r_foreign)
```

## Hedge Effectiveness (IAS 39 / IFRS 9)
```
Effectiveness = ΔV_hedge / ΔV_hedged_item
```
Must be 80-125% for hedge accounting qualification.
