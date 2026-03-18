# WACC — Fundamentos

## Fórmula General

WACC = Ke × (E/V) + Kd × (1 − t) × (D/V)

Donde:
- Ke = coste del equity (accionistas)
- Kd = coste de la deuda (antes de impuestos)
- E = valor de mercado del equity
- D = valor de mercado de la deuda financiera neta
- V = E + D (valor total de la empresa)
- t = tasa impositiva efectiva

## Coste del Equity — CAPM

Ke = Rf + β × Pm

- Rf = tasa libre de riesgo (bono soberano 10Y)
- β = beta del activo (sensibilidad al mercado)
- Pm = prima de riesgo de mercado (equity risk premium)

### Beta apalancada vs. desapalancada

β_L = β_U × [1 + (D/E) × (1 − t)]

- β_U = beta desapalancada (comparable de sector, sin efecto financiero)
- β_L = beta apalancada (refleja estructura de capital de la empresa)

## Referencia España (2026)

- Rf: bono español 10Y ≈ 3.1–3.4%
- Prima de riesgo España (Damodaran): ≈ 6.0–6.5%
- Prima de riesgo mercado IBEX (histórico 20Y): ≈ 5.5–6.0%
- Beta sectorial media (industriales IBEX): 0.85–1.10
- Tasa impositiva IS España: 25% (efectiva suele ser 20–23%)

## Coste de la Deuda

Kd = tipo de interés medio ponderado de la deuda financiera

Fuentes en orden de preferencia:
1. Intereses financieros / deuda financiera media (P&L / balance)
2. Rating crediticio → spread sobre swap rate
3. Proxy: Euribor 12M + spread sectorial

Kd neto de impuestos = Kd × (1 − t)

## Ejemplo Numérico — Empresa Industrial Española

Datos:
- Equity: 800 M€, Deuda neta: 400 M€ → V = 1.200 M€
- Rf = 3.2%, β_L = 0.95, Pm = 6.0%
- Kd = 4.5%, t = 23%

Cálculo:
- Ke = 3.2% + 0.95 × 6.0% = 8.9%
- Kd neto = 4.5% × (1 − 0.23) = 3.5%
- Ponderaciones: E/V = 67%, D/V = 33%
- WACC = 8.9% × 0.67 + 3.5% × 0.33 = **7.1%**

## Consideraciones CNMV / Regulatorias

- Informes de valoración para OPAs deben justificar Rf y prima de riesgo
- Beta: usar media 2Y semanal o 5Y mensual (fuente: Bloomberg, Reuters)
- Si empresa no cotiza: β desapalancada de peers cotizados + reapalancamiento
- CNMV exige sensibilidad del valor final a ±0.5% en WACC en informes de OPA

## Sensibilidad del WACC

Regla práctica: ±1% en WACC → ±15–25% en valoración DCF
Factores que más mueven el WACC:
1. Beta (especialmente en ciclo económico)
2. Prima de riesgo de mercado (revisión anual Damodaran)
3. Estructura D/E objetivo (si cambia el apalancamiento)
