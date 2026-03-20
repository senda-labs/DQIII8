# Risk Management Fundamentals

## Definition
Risk management is the systematic process of identifying, assessing, and controlling threats to an organization's capital and earnings. Financial risk management focuses on quantifying and hedging market, credit, liquidity, and operational risks.

## Core Concepts

- **Risk Types:**
  - Market risk: Loss from adverse price movements (equity, interest rates, FX, commodities).
  - Credit risk: Counterparty defaults on obligations.
  - Liquidity risk: Inability to liquidate positions without significant price impact, or fund operations.
  - Operational risk: Losses from failed internal processes, systems, people, or external events.
  - Systemic risk: Risk of collapse of an entire financial system.
- **Value at Risk (VaR):** Statistical measure of potential loss. "With 99% confidence, maximum loss over 1 day is $X." Three methods: historical simulation, parametric (variance-covariance), Monte Carlo.
  - Limitation: Does not capture tail risk beyond the confidence level.
- **Expected Shortfall (CVaR):** Average loss beyond the VaR threshold. Better captures tail risk than VaR.
- **Volatility:** Standard deviation of returns. Historical volatility (from past returns) vs. implied volatility (from option prices). GARCH models capture volatility clustering.
- **Hedging:** Offsetting risk using derivatives. Delta hedging (options), interest rate swaps, currency forwards. Perfect hedge eliminates risk but also upside.
- **Diversification:** Portfolio theory (Markowitz). Combining uncorrelated assets reduces portfolio variance. Correlation matrix is key. Only systematic risk (beta) is priced; unsystematic risk is diversifiable.
- **Stress Testing and Scenario Analysis:** Simulate extreme but plausible events. Basel III requires banks to conduct stress tests. DFAST (Dodd-Frank) and CCAR in the US.
- **Basel Accords:** International regulatory frameworks. Basel III requires banks to hold sufficient Tier 1 capital (CET1 >= 4.5% of risk-weighted assets), liquidity ratios (LCR, NSFR).

## Key Formulas
- Portfolio variance: σ^2_p = w1^2σ1^2 + w2^2σ2^2 + 2w1*w2*σ1*σ2*ρ
- Sharpe ratio: (Rp - Rf) / σp — return per unit of total risk
- Beta: β = Cov(Ri, Rm) / Var(Rm)

## Practical Applications
- **Banks:** Capital requirement calculation, credit scoring, loan provisioning.
- **Hedge funds:** Greeks management (delta, gamma, vega, theta), systematic risk models.
- **Corporates:** FX hedging, interest rate swaps to manage debt exposure.
- **Insurance:** Actuarial risk modeling, catastrophe models.
