---
name: binance-spot
description: Binance Spot API skill for systematic trading. Provides K-line/candlestick data, spot order placement (MARKET/LIMIT/OCO), account info, and trade history. Use for backtesting data ingestion, live order execution, and portfolio tracking.
source: binance/binance-skills-hub/skills/binance/spot
reviewed: 2026-03-18
approved_by: Iker + Claude
status: APROBADA
---

# Binance Spot API — JARVIS Trading Skill

## Scope Adjustment for JARVIS Stack

- **Primary use**: trading-sistemático project — backtesting data + live execution
- **Testnet first**: always validate strategies on Binance testnet before mainnet
- **Auth**: `BINANCE_API_KEY` + `BINANCE_SECRET_KEY` in `.env` — never hardcode
- **High priority**: K-lines (historical data), spot orders, account balance
- **Low priority**: WebSocket streams (handled separately in real-time pipeline)

## Base URLs

```
Mainnet: https://api.binance.com
Testnet: https://testnet.binance.vision
```

## Key Endpoints for Systematic Trading

### Market Data (no auth)

| Endpoint | Method | Description | Key Params |
|----------|--------|-------------|------------|
| `/api/v3/klines` | GET | K-Line/Candlestick data | `symbol`, `interval`, `startTime`, `endTime`, `limit` |
| `/api/v3/ticker/24hr` | GET | 24hr price change stats | `symbol` |
| `/api/v3/ticker/price` | GET | Current price | `symbol` |
| `/api/v3/depth` | GET | Order book | `symbol`, `limit` |
| `/api/v3/aggTrades` | GET | Compressed trades | `symbol`, `startTime`, `endTime` |
| `/api/v3/exchangeInfo` | GET | Symbol info, filters, precision | `symbol` |

### Intervals for K-Lines

`1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`

### K-Line Response Format

```
[
  [
    1499040000000,  # Open time (ms)
    "0.01634790",   # Open
    "0.80000000",   # High
    "0.01575800",   # Low
    "0.01577100",   # Close
    "148976.11427815", # Volume
    1499644799999,  # Close time (ms)
    "2434.19055334", # Quote asset volume
    308,            # Number of trades
    "1756.87402397", # Taker buy base asset volume
    "28.46694368",  # Taker buy quote asset volume
    "0"             # Unused
  ]
]
```

### Account & Orders (auth required)

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/api/v3/account` | GET | Balances, commission rates | Yes |
| `/api/v3/myTrades` | GET | Trade history | Yes |
| `/api/v3/allOrders` | GET | All orders (open + closed) | Yes |
| `/api/v3/openOrders` | GET | Current open orders | Yes |
| `/api/v3/order` | POST | Place new order | Yes |
| `/api/v3/order` | DELETE | Cancel order | Yes |
| `/api/v3/order` | GET | Query order status | Yes |
| `/api/v3/order/test` | POST | Test order (no execution) | Yes |

### Order Placement Parameters

```python
# MARKET order
{
    "symbol": "BTCUSDT",
    "side": "BUY",          # BUY | SELL
    "type": "MARKET",
    "quantity": "0.001"
}

# LIMIT order
{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "timeInForce": "GTC",   # GTC | IOC | FOK
    "quantity": "0.001",
    "price": "50000.00"
}

# STOP_LOSS_LIMIT
{
    "symbol": "BTCUSDT",
    "side": "SELL",
    "type": "STOP_LOSS_LIMIT",
    "timeInForce": "GTC",
    "quantity": "0.001",
    "price": "49000.00",
    "stopPrice": "49500.00"
}
```

## Python Implementation Pattern (JARVIS stack)

```python
import hmac
import hashlib
import time
import os
import httpx
from pathlib import Path

BINANCE_BASE = os.environ["BINANCE_BASE_URL"]  # testnet or mainnet
API_KEY = os.environ["BINANCE_API_KEY"]
SECRET_KEY = os.environ["BINANCE_SECRET_KEY"]

def sign(params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return hmac.new(SECRET_KEY.encode(), query.encode(), hashlib.sha256).hexdigest()

async def get_klines(symbol: str, interval: str, limit: int = 500) -> list:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit}
        )
        r.raise_for_status()
        return r.json()

async def place_order(symbol: str, side: str, order_type: str, **kwargs) -> dict:
    params = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "timestamp": int(time.time() * 1000),
        **kwargs
    }
    params["signature"] = sign(params)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BINANCE_BASE}/api/v3/order",
            headers={"X-MBX-APIKEY": API_KEY},
            params=params
        )
        r.raise_for_status()
        return r.json()
```

## Rate Limits

- Market data: 1200 weight/min (klines = 2 weight per call)
- Orders: 100 orders/10s per symbol, 200,000 orders/24h
- Always check `X-MBX-USED-WEIGHT-1M` header in responses

## JARVIS Trading Rules

1. Always use testnet (`testnet.binance.vision`) for strategy validation
2. Store `BINANCE_API_KEY` and `BINANCE_SECRET_KEY` in `.env` only
3. Log every order to `jarvis_metrics.db` (table: `trading_orders`)
4. Never use market orders for large sizes — use LIMIT with slippage tolerance
5. Max position size per trade: configure in strategy config, not hardcoded
