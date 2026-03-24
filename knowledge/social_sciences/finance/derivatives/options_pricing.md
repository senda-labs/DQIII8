# Options Pricing

## Black-Scholes-Merton (European options)
```
C = S×N(d1) - K×e^(-rT)×N(d2)
P = K×e^(-rT)×N(-d2) - S×N(-d1)

d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)
d2 = d1 - σ√T
```
- S: spot price, K: strike, r: risk-free rate
- T: time to expiry (years), σ: implied volatility
- N(): cumulative normal distribution

## Put-Call Parity
```
C - P = S - K×e^(-rT)
```
Arbitrage relationship. If violated, riskless profit exists.

## Binomial Model (American options)
1. Build price tree: u = e^(σ√Δt), d = 1/u
2. Risk-neutral probability: p = (e^(rΔt) - d)/(u - d)
3. Calculate payoff at terminal nodes
4. Backward induction: check early exercise at each node
5. American option ≥ European option (early exercise premium)

## Monte Carlo for Options
- Simulate N paths of underlying price
- Calculate payoff per path
- Average discounted payoffs = option price
- Standard error decreases as 1/√N

## Assumptions / Limitations
- BSM assumes: constant vol, no dividends, European exercise, no jumps
- Real markets: vol smile/skew, stochastic vol, jump-diffusion
