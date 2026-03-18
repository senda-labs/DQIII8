---
project: trading-sistematico
status: PLANIFICADO
phase: 0 — setup
created: 2026-03-18
owner: Iker
---

# Trading Sistemático — Proyecto JARVIS

## Objetivo

Desarrollar un sistema de trading algorítmico/sistemático sobre Binance Spot, con backtesting riguroso, gestión de riesgo cuantitativa y ejecución automatizada.

Perfil del usuario: Iker — título en Finanzas y Contabilidad (Universidad Carlos III de Madrid). Conocimiento de WACC, DCF, fiscalidad española, contabilidad de costes, economía. Trading sistemático como proyecto a largo plazo.

## Stack Técnico

- **Lenguaje**: Python 3.12 (Black, pathlib, async, type hints)
- **Datos**: Binance API (`/api/v3/klines`) + ccxt como alternativa multi-exchange
- **Backtesting**: vectorbt (vectorizado, rápido) o backtrader (event-driven)
- **Análisis estadístico**: pandas, numpy, scipy, statsmodels (ARIMA, GARCH)
- **Riesgo**: pyfolio, quantstats — Sharpe, Sortino, max drawdown, VaR, CVaR
- **DB**: jarvis_metrics.db (tabla `trading_strategies` + `trading_orders`)
- **Exchange**: Binance Spot API — testnet primero, mainnet después de validación

## Agentes Asignados

| Agente | Rol | Cuándo usar |
|--------|-----|-------------|
| quant-analyst | Diseño de estrategias, backtesting, métricas, Monte Carlo | Toda la fase de research y validación |
| fintech-engineer | Infraestructura de ejecución, order management, exchange API | Fase de implementación live |
| risk-manager | Framework de riesgo, VaR, position sizing, stop-loss | Antes de cualquier capital real |
| data-analyst | Análisis exploratorio de datos OHLCV, correlaciones | EDA inicial |
| python-specialist | Implementación de código (Tier 1 local: qwen2.5-coder) | Toda la codificación |
| code-reviewer | Review de código de estrategias (vibesec activo) | Antes de live |

## Skills Asignadas

- `binance-spot` — API reference completa para datos + ejecución
- `binance/trading-signal` — Smart Money signals on-chain (referencia)
- `binance/query-token-info` — Market data adicional (referencia)
- Pendiente: `quant-sentiment-ai/claude-equity-research` — análisis fundamental

## Fases del Proyecto

### Fase 1 — Data Pipeline (pendiente inicio)

1. Crear worktree: `trading-sistematico`
2. Estructura de carpetas:
   ```
   trading-sistematico/
   ├── data/          # OHLCV raw data
   ├── strategies/    # Strategy definitions
   ├── backtests/     # Backtest results
   ├── live/          # Live trading engine
   ├── risk/          # Risk management
   └── notebooks/     # Analysis notebooks
   ```
3. Implementar `data/binance_fetcher.py`:
   - Descarga histórica de K-lines (BTC, ETH, top altcoins)
   - Almacenamiento en SQLite/Parquet
   - Rate limiting automático (1200 weight/min)
4. Tests: pytest con datos mock de Binance

### Fase 2 — Estrategias y Backtesting (pendiente)

Estrategias candidatas (por complejidad ascendente):
1. **Moving Average Crossover** — baseline simple, EMA(9)/EMA(21)
2. **Mean Reversion** — RSI extremos + Bollinger Bands
3. **Momentum** — Rate of Change + volumen
4. **Statistical Arbitrage** — cointegración de pares (BTC/ETH spread)
5. **GARCH Volatility** — posicionamiento basado en volatilidad predicha

Métricas de validación (quant-analyst):
- Sharpe ratio > 1.5 (mínimo para considerar viable)
- Max drawdown < 15%
- Win rate + profit factor
- VaR 95% y 99%
- Calmar ratio
- Out-of-sample performance (walk-forward optimization)

### Fase 3 — Risk Framework (pendiente)

- Position sizing: Kelly Criterion adaptado (half-Kelly)
- Stop-loss: basado en ATR o fixed percentage
- Portfolio-level VaR: Monte Carlo + historical simulation
- Maximum correlation entre posiciones abiertas
- Circuit breakers: max daily loss, max drawdown trigger

### Fase 4 — Live Execution (pendiente)

- Paper trading en Binance Testnet mínimo 30 días
- Comparación backtest vs paper trading (slippage, fees)
- Gestión de API keys (rotación, permisos mínimos: spot trading only)
- Logging completo a jarvis_metrics.db
- Telegram alerts para fills, stops, errores

## Reglas de Riesgo (inmutables)

1. **NUNCA** poner capital real sin 30 días de paper trading validado
2. **NUNCA** hardcodear API keys — siempre `.env`
3. **SIEMPRE** testnet primero, mainnet después de sign-off de risk-manager
4. **NUNCA** usar market orders para posiciones > 0.1 BTC equivalente
5. **SIEMPRE** position sizing máximo: 5% del portfolio por trade
6. **SIEMPRE** stop-loss definido antes de entrar a la posición

## Fiscalidad Española (nota)

- Ganancias de crypto: tributación en IRPF como ganancia patrimonial
- Plazos: < 1 año = base general (hasta 47%), > 1 año = base ahorro (19-26%)
- Obligación de declarar: independientemente del importe
- Herramienta de seguimiento: necesaria para FIFO/LIFO y cálculo de plusvalías

## Próximo Paso

Cuando Iker diga "empezamos trading-sistemático", ejecutar:
1. `git worktree add ../trading-sistematico -b trading-sistematico`
2. Instalar dependencias: `pip install ccxt vectorbt pyfolio quantstats statsmodels`
3. Iniciar con Fase 1 — Data Pipeline
