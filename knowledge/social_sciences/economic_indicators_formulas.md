---
domain: social_sciences
agent: economics-specialist
keywords_es: [PIB, inflación, Phillips, IS-LM, multiplicador, tipo interés, política monetaria, fiscal, Taylor, tipo cambio, NAIRU, Okun, paridad]
keywords_en: [GDP, inflation, Phillips, IS-LM, multiplier, interest rate, monetary policy, fiscal, Taylor rule, exchange rate, NAIRU, Okun, parity]
---

# Economic Indicators — Formulas & Calibrated Parameters

## National Accounts

```
GDP Expenditure: Y = C + I + G + NX   (NX = X - M)
GDP Income: Y = W + R + i + Pi (wages + rent + interest + profit)
GDP Output: sum of value-added across sectors

GNP = GDP + Net factor income from abroad
GNI ≈ GNP (modern terminology)

Nominal GDP vs Real GDP:
  GDP deflator = (Nominal GDP / Real GDP) × 100
  GDP deflator ≠ CPI: deflator covers ALL domestic goods; CPI only fixed consumption basket

Potential GDP: Y* estimated via Hodrick-Prescott filter (lambda=1600 for quarterly)
Output gap: (Y - Y*) / Y* × 100 %
```

## IS-LM Model

```
IS curve: Y = C + I + G + NX
  C = C0 + c*(Y - T)   [c = MPC, 0 < c < 1]
  I = I0 - b*i          [b = interest sensitivity]

  IS: Y = [1/(1-c)] * (C0 + I0 - b*i + G - c*T)
  Fiscal multiplier: dY/dG = 1/(1-c)    [simple, no taxes]
  With taxes: dY/dG = 1/(1-c*(1-t))
  Tax multiplier: dY/dT = -c/(1-c*(1-t))

  Calibration example: c=0.80, t=0.30
    Fiscal multiplier = 1/(1-0.8*0.7) = 1/0.44 = 2.27
    Balanced budget multiplier = 1 (always, regardless of c)

LM curve: M/P = L(Y,i) = k*Y - h*i
  i = (k*Y - M/P) / h
  Money demand interest elasticity (h): 0.5–1.0 (typical calibration)
  Money demand income elasticity (k): 0.5–1.0
```

## Fiscal Multipliers (Empirical, Post-GFC)

| Context | Multiplier | Source |
|---------|-----------|--------|
| US stimulus (2009) | 1.5–2.0 | CBO estimates |
| Eurozone austerity (2010–2012) | 1.0–1.7 (much higher than IMF predicted) | Blanchard & Leigh (2013) |
| Zero lower bound (ZLB) | 2.0–3.0 | enhanced fiscal effectiveness |
| Normal times, small open economy | 0.5–0.8 | crowding out + import leakage |

## Phillips Curve (Modern Specification)

```
New Keynesian Phillips Curve:
  pi = pi_e + kappa*(y - y*) + epsilon   [forward-looking]
  pi = pi_{t-1} - beta*(u - u_n) + epsilon  [backward-looking]

Parameters (US calibration, 2015–2023):
  beta (slope): 0.1–0.4 (flatter than 1970s; ~0.5 pre-1990)
  kappa: 0.05–0.15

NAIRU estimates (2024–2025):
  US: ~4.0–4.1% (CBO)
  Eurozone: ~6.3% (ECB)
  UK: ~4.3% (OBR)
  Germany: ~3.0%
  Spain: ~11–13% (structural)
```

## Taylor Rule

```
i = r* + pi + phi_pi*(pi - pi*) + phi_y*(y - y*)

Standard coefficients (Taylor 1993):
  phi_pi = 1.5  [response to inflation gap]
  phi_y = 0.5   [response to output gap]

Current parameters (2024–2025):
  r* (neutral real rate): 0.5–1.5% (debate: Holston-Laubach-Williams)
  pi* (target): 2.0% (Fed, ECB, BoE)

Rule implies (if pi=4%, y gap=+2%): i = 1.0 + 4.0 + 1.5*(4-2) + 0.5*2 = 9.0%
Actual Fed funds (2023): 5.25–5.50% → rule prescribes higher rates
```

## Exchange Rate Parities

```
Purchasing Power Parity (PPP):
  Absolute: P = e * P*   (price levels, adjusted by exchange rate)
  Relative: %Δe = pi - pi*  (differential inflation = depreciation)

Uncovered Interest Parity (UIP):
  E[Δs] = i - i*   (expected depreciation = interest differential)

Covered Interest Parity (CIP): holds well pre-GFC; broke down 2008–2020
  Forward premium: f - s = i - i*

Real exchange rate: q = s + p* - p   (s = log nominal rate)
Real effective exchange rate (REER): trade-weighted average
```

## Okun's Law

```
Relationship between output growth and unemployment:
  delta_u ≈ -0.5 * (delta_%Y - g*)

  g* = potential growth rate (~1.8–2.0% US, ~1.0–1.5% Eurozone)

  Interpretation: 1 percentage point above potential → 0.5pp less unemployment

Okun coefficient (-0.5) has declined post-2000 (more labor hoarding; gig economy)
Some estimates: -0.3 to -0.4 in recent cycles
```

## FRED Variable Codes

| Variable | FRED Code | Frequency |
|----------|-----------|-----------|
| Real GDP | GDPC1 | Quarterly |
| Nominal GDP | GDP | Quarterly |
| CPI All Items | CPIAUCSL | Monthly |
| Core PCE | PCEPILFE | Monthly |
| Unemployment Rate | UNRATE | Monthly |
| Fed Funds Rate (target) | FEDFUNDS | Monthly |
| 10Y Treasury Yield | DGS10 | Daily |
| 2Y Treasury Yield | DGS2 | Daily |
| M2 Money Supply | M2SL | Monthly |
| Personal Saving Rate | PSAVERT | Monthly |
| Industrial Production | INDPRO | Monthly |
| ISM Manufacturing PMI | MANEMP | — |
| TED Spread | TEDRATE | Daily |
| USD Trade-Weighted Index | DTWEXBGS | Daily |

Recession indicator (NBER-dated): USREC (1 = recession, 0 = expansion)

**Source:** Mankiw "Macroeconomics" 11th ed. (2022) + FRED (fred.stlouisfed.org) + Blanchard & Leigh (2013) IMF WP/13/1
