# DCF — Metodología

## Concepto

El DCF (Discounted Cash Flow) valora una empresa como el valor presente
de sus flujos de caja libre futuros descontados al WACC.

EV = Σ [FCFt / (1 + WACC)^t] + VT / (1 + WACC)^n

## Flujo de Caja Libre (FCF)

FCF = EBIT × (1 − t) + D&A − CAPEX − ΔFCK

Donde:
- EBIT × (1 − t) = NOPAT (beneficio operativo neto de impuestos)
- D&A = depreciación y amortización (no caja, se suma)
- CAPEX = inversión en activo fijo (salida de caja)
- ΔFCK = variación del fondo de comercio / capital circulante neto

### Capital Circulante Neto (CCN)

CCN = (Clientes + Existencias) − Proveedores
ΔFCK positivo = más capital inmovilizado → reduce FCF

## Valor Terminal (Gordon Growth)

VT = FCFn × (1 + g) / (WACC − g)

- g = tasa de crecimiento perpetuo (típico: 1.5–2.5% en Europa)
- g debe ser ≤ crecimiento nominal del PIB del sector
- Regla: VT suele representar 60–80% del EV total → muy sensible

### Alternativa: Múltiplo de Salida

VT = EBITDAn × múltiplo_sector

Útil para validación cruzada con el método Gordon.

## Del EV al Equity Value

Equity Value = EV − Deuda Neta + Activos No Operativos

Deuda Neta = Deuda financiera bruta − Caja y equivalentes

## Horizonte y Fases

Fase 1 (años 1–5): proyección explícita de P&L + FCF
Fase 2 (años 6–10, opcional): crecimiento convergente hacia g
Fase 3: valor terminal

Para empresas en crecimiento: usar 2 fases con WACC más alto en fase 1.

## Análisis de Sensibilidad

Tabla 2D obligatoria en cualquier DCF profesional:

|        | g=1.0% | g=1.5% | g=2.0% | g=2.5% |
|--------|--------|--------|--------|--------|
| W=6.0% |        |        |        |        |
| W=6.5% |        |   BASE |        |        |
| W=7.0% |        |        |        |        |
| W=7.5% |        |        |        |        |

Regla práctica:
- +1% WACC → −15 a −25% en EV
- +0.5% g → +10 a +15% en EV

## Limitaciones del Modelo

1. Sensibilidad extrema a g y WACC (pequeños cambios → gran impacto)
2. Proyecciones de FCF > 5Y tienen alta incertidumbre
3. Ignora opciones reales (expansión, desinversión)
4. Para empresas cíclicas: usar FCF normalizado, no el puntual
5. CAPEX de mantenimiento vs. crecimiento deben separarse
6. Valores negativos de FCF en años iniciales son válidos (crecimiento)

## Validación Cruzada

Siempre contrastar DCF con valoración por múltiplos:
- Si DCF da EV/EBITDA implícito >> peers → revisar supuestos de g o margen
- Diferencia tolerable DCF vs. múltiplos: ±20%
- Diferencia > 30% → identificar y justificar el driver principal
