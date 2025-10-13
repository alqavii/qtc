# QTC Alpha Trading Platform - Complete System Documentation

**Version:** 1.0  
**Last Updated:** October 10, 2025

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [How Everything Works](#how-everything-works)
4. [Trading Strategies](#trading-strategies)
5. [Data Flow](#data-flow)
6. [Performance & Metrics](#performance--metrics)
7. [API Reference](#api-reference)
8. [FAQ - Frequently Asked Questions](#faq---frequently-asked-questions)
9. [Troubleshooting](#troubleshooting)
10. [Deployment Guide](#deployment-guide)

---

## System Overview

### What is QTC Alpha?

QTC Alpha is a **competitive algorithmic trading platform** where multiple teams compete by deploying trading strategies (bots) that execute trades on real financial markets via Alpaca.

**Key Features:**
- 🤖 **Automated Trading** - Strategies execute every minute during market hours
- 📊 **Real-time Competition** - Public leaderboard shows team rankings
- 🔒 **Secure Execution** - Sandboxed strategy environment with strict security
- 📈 **Performance Tracking** - Comprehensive metrics (Sharpe, Sortino, drawdown, etc.)
- 🌐 **API Access** - RESTful API for teams and public access
- 💰 **Real Money Trading** - Uses Alpaca broker (paper or live trading)

---

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    QTC ALPHA PLATFORM                        │
│                                                              │
│  ┌──────────────┐     ┌─────────────┐     ┌──────────────┐ │
│  │ ORCHESTRATOR │────▶│   ALPACA    │────▶│    MARKET    │ │
│  │   (Brain)    │     │   BROKER    │     │  (NYSE, etc) │ │
│  └──────────────┘     └─────────────┘     └──────────────┘ │
│         ↓ ↑                                                  │
│    ┌────────────┐                                           │
│    │ STRATEGIES │  ← Team Trading Algorithms                │
│    │  (Bots)    │                                           │
│    └────────────┘                                           │
│         ↓                                                    │
│    ┌────────────┐                                           │
│    │   DATA     │  ← Portfolio, Trades, Metrics             │
│    │  STORAGE   │                                           │
│    └────────────┘                                           │
│         ↓                                                    │
│    ┌────────────┐                                           │
│    │  REST API  │  ← Public & Team Access                   │
│    └────────────┘                                           │
│         ↓                                                    │
│    ┌────────────┐                                           │
│    │  FRONTEND  │  ← Leaderboard, Dashboards                │
│    └────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture

### Technology Stack

**Backend:**
- **Python 3.12+** - Core language
- **FastAPI** - REST API framework
- **Pandas/NumPy** - Data processing
- **PyArrow/Parquet** - Efficient data storage
- **Alpaca-py** - Broker integration

**Data Storage:**
- **JSONL** - Real-time streaming data (trades, snapshots)
- **Parquet** - Historical data (daily consolidation)
- **JSON** - Configuration (API keys, registry)
- **YAML** - Team registry

**Infrastructure:**
- **Uvicorn** - ASGI server
- **Nginx** (optional) - Reverse proxy
- **Systemd** (optional) - Process management

---

### Directory Structure

```
/opt/qtc/
├── app/
│   ├── adapters/
│   │   ├── alpaca_broker.py      # Trading client wrapper
│   │   ├── ticker_adapter.py     # Market data fetcher
│   │   └── parquet_writer.py     # Data persistence
│   ├── api/
│   │   └── server.py             # FastAPI REST API
│   ├── config/
│   │   ├── environments.py       # Environment config
│   │   └── settings.py           # Global settings
│   ├── loaders/
│   │   ├── git_fetch.py          # Strategy sync from Git
│   │   ├── strategy_loader.py    # Dynamic strategy loading
│   │   └── static_check.py       # Security validation
│   ├── models/
│   │   ├── teams.py              # Team/Portfolio models
│   │   ├── trading.py            # Trade models
│   │   └── ticker_data.py        # Market data models
│   ├── services/
│   │   ├── auth.py               # API key management
│   │   ├── trade_executor.py     # Trade execution
│   │   ├── minute_service.py     # Minute scheduler
│   │   └── market_hours.py       # Market hours checker
│   ├── performance/
│   │   └── performance_tracker.py # Metrics calculation
│   └── main.py                   # Main orchestrator
│
├── data/
│   ├── api_keys.json             # Team API keys
│   ├── team/{team_id}/
│   │   ├── trades.jsonl          # Trade log
│   │   ├── portfolio/*.jsonl     # Minute snapshots
│   │   ├── portfolio.parquet     # Historical data
│   │   └── metrics.jsonl         # Performance metrics
│   ├── qtc-alpha/                # Account-level data
│   └── prices/minute_bars/       # Market data cache
│
├── external_strategies/
│   └── {team_id}/
│       └── strategy.py           # Active strategy code
│
├── team_registry.yaml            # Team configuration
└── requirements.txt              # Python dependencies
```

---

## How Everything Works

### The Trading Cycle (Every Minute)

**Duration:** ~5-10 seconds per cycle  
**Frequency:** Every minute during market hours (9:30 AM - 4:00 PM ET)

```
┌─────────────────────────────────────────────────────────────┐
│  MINUTE TICK (e.g., 9:31:00 AM)                             │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 1. Fetch Market Data │ (~500ms)
    │    from Alpaca       │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 2. Load Strategies   │ (~100ms per team)
    │    for all teams     │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 3. Execute Strategies│ (~50ms per team)
    │    generate_signal() │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 4. Validate Signals  │ (~10ms per signal)
    │    Security checks   │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 5. Execute Trades    │ (~200ms per order)
    │    Submit to Alpaca  │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 6. Update Portfolios │ (~50ms per team)
    │    Calculate values  │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 7. Save Data         │ (~100ms)
    │    JSONL + Metrics   │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 8. Update API Cache  │ (~10ms)
    │    Latest values     │
    └──────────────────────┘
```

**Total Time:** ~2-5 seconds (depending on number of teams and trades)

---

### Detailed Process Flow

#### Step 1: Market Data Fetch

**What happens:**
```python
# app/adapters/ticker_adapter.py
bars = TickerAdapter().fetchBasic()
# Returns: List of MinuteBar objects
# Example: [MinuteBar(ticker='AAPL', close=150.25, volume=1000000, ...)]
```

**Latency:** ~300-800ms (Alpaca API call)

**What's fetched:**
- Latest minute bars for all symbols in universe
- OHLCV data (Open, High, Low, Close, Volume)
- Timestamp aligned to minute boundary

---

#### Step 2: Strategy Loading

**What happens:**
```python
# app/loaders/strategy_loader.py
strategy = load_strategy_from_folder(
    folder="/opt/qtc/external_strategies/team1",
    entry_point="strategy:Strategy"
)
```

**Security checks:**
- ✅ AST parsing (no dangerous imports)
- ✅ No file I/O operations
- ✅ No network access
- ✅ No subprocess calls
- ✅ No eval/exec
- ✅ Timeout enforcement (5 seconds max)

**Allowed imports:**
- `numpy`, `pandas`, `scipy` - Math/data processing
- `datetime`, `time` - Time operations
- `typing`, `dataclasses` - Type hints
- `collections`, `itertools` - Standard collections

**Blocked:**
- `requests`, `urllib`, `socket` - Network
- `open`, `write`, `os.path` - File I/O
- `subprocess`, `os.system` - System calls
- `eval`, `exec`, `__import__` - Dynamic code execution

---

#### Step 3: Strategy Execution

**What happens:**
```python
# Each team's strategy.generate_signal() is called
signal = strategy.generate_signal(
    team={
        "id": "team1",
        "cash": 50000.0,
        "params": {"risk_level": 0.5}
    },
    bars={
        "AAPL": {
            "timestamp": ["2025-10-10T09:31:00Z"],
            "open": [150.0],
            "high": [150.5],
            "low": [149.8],
            "close": [150.25],
            "volume": [1000000]
        }
    },
    current_prices={
        "AAPL": 150.25,
        "NVDA": 500.50
    }
)

# Returns: {"symbol": "AAPL", "action": "buy", "quantity": 10, "price": 150.25}
# Or: None (no trade)
```

**Timeout:** 5 seconds per strategy
- If exceeded, strategy is killed
- No trade executed for that minute
- Error logged

---

#### Step 4: Signal Validation

**Checks performed:**
```python
# 1. Schema validation
StrategySignal.model_validate(signal)

# 2. Symbol validation
assert signal['symbol'] in TICKER_UNIVERSE

# 3. Action validation
assert signal['action'] in ['buy', 'sell']

# 4. Quantity validation
assert signal['quantity'] > 0

# 5. Price reasonableness (within 10% of current price)
assert abs(signal['price'] - current_prices[signal['symbol']]) / current_prices[signal['symbol']] < 0.10

# 6. Cash/position check
if signal['action'] == 'buy':
    assert team.cash >= signal['quantity'] * signal['price']
if signal['action'] == 'sell':
    assert team.positions[signal['symbol']].quantity >= signal['quantity']
```

---

#### Step 5: Trade Execution

**What happens:**
```python
# app/services/trade_executor.py
success, message = trade_executor.execute(team, trade_request)

# If Alpaca credentials configured:
order_id = alpaca_broker.placeMarketOrder(
    symbol="AAPL",
    side="buy",
    quantity=10,
    clientOrderId="team1-20251010093100123"
)

# Client Order ID format: {team_id}-{timestamp}
# This prevents mixing trades between teams
```

**Order execution:**
1. **Market hours check** - Only during 9:30 AM - 4:00 PM ET
2. **Local portfolio update** - Immediate
3. **Alpaca order submission** - If credentials present
4. **Trade logging** - Append to trades.jsonl

**Latency:**
- Local update: ~1ms
- Alpaca API call: ~100-300ms
- Order fill: ~50-500ms (market conditions)

---

#### Step 6: Portfolio Update

**What happens:**
```python
# Update portfolio state
portfolio.cash -= (quantity * price)  # For buy
portfolio.positions[symbol].quantity += quantity
portfolio.positions[symbol].avg_cost = new_average

# Calculate market value
market_value = portfolio.cash + sum(
    position.quantity * current_prices[position.symbol]
    for position in portfolio.positions
)
```

**Data collected:**
- Cash remaining
- Position quantities and values
- Market value (total portfolio worth)
- Unrealized P&L per position
- Timestamp

---

#### Step 7: Data Persistence

**What's saved:**

**1. Trades (trades.jsonl):**
```json
{
  "timestamp": "2025-10-10T09:31:00+00:00",
  "team_id": "team1",
  "symbol": "AAPL",
  "side": "buy",
  "quantity": 10,
  "price": 150.25,
  "value": 1502.50,
  "order_id": "abc123-alpaca-order-id"
}
```

**2. Portfolio Snapshots (portfolio/YYYY-MM-DD.jsonl):**
```json
{
  "timestamp": "2025-10-10T09:31:00+00:00",
  "cash": 48497.50,
  "market_value": 50000.00,
  "positions": {
    "AAPL": {
      "quantity": 10,
      "avg_cost": 150.25,
      "current_price": 150.25,
      "value": 1502.50,
      "unrealized_pl": 0.0
    }
  }
}
```

**3. Metrics (metrics.jsonl):**
```json
{
  "timestamp": "2025-10-10T09:31:00+00:00",
  "total_trades": 5,
  "win_rate": 0.60,
  "total_return": 0.025
}
```

**Daily Consolidation:**
- At UTC midnight, JSONL files are converted to Parquet
- Parquet files are much smaller and faster to query
- JSONL files are deleted after successful conversion

---

## Trading Strategies

### Strategy Interface

Every strategy must implement this interface:

```python
class Strategy:
    def __init__(self, **kwargs):
        """Initialize strategy with optional parameters."""
        # Access team parameters
        self.risk_level = kwargs.get('risk_level', 0.5)
        
    def generate_signal(
        self, 
        team: dict, 
        bars: dict, 
        current_prices: dict
    ) -> dict | None:
        """Generate trading signal.
        
        Args:
            team: {
                "id": str,           # Team identifier
                "cash": float,       # Available cash
                "params": dict,      # Strategy parameters
                "api": DataAPI       # Read-only data access
            }
            bars: {
                "SYMBOL": {
                    "timestamp": [datetime, ...],
                    "open": [float, ...],
                    "high": [float, ...],
                    "low": [float, ...],
                    "close": [float, ...],
                    "volume": [int, ...]
                }
            }
            current_prices: {
                "SYMBOL": float  # Latest price
            }
        
        Returns:
            Signal dict or None:
            {
                "symbol": "AAPL",
                "action": "buy" | "sell",
                "quantity": 10,
                "price": 150.25,
                "confidence": 0.8,     # Optional
                "reason": "MA cross"   # Optional
            }
        """
        # Your trading logic here
        if some_condition:
            return {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": 10,
                "price": current_prices["AAPL"]
            }
        
        return None  # No trade this minute
```

---

### Example Strategy: Moving Average Crossover

```python
class Strategy:
    def __init__(self, **kwargs):
        self.symbol = kwargs.get('symbol', 'AAPL')
        self.fast_period = kwargs.get('fast_period', 10)
        self.slow_period = kwargs.get('slow_period', 30)
        self.quantity = kwargs.get('quantity', 10)
        
    def generate_signal(self, team, bars, current_prices):
        # Get data for our symbol
        if self.symbol not in bars:
            return None
            
        data = bars[self.symbol]
        closes = data.get('close', [])
        
        # Need enough data
        if len(closes) < self.slow_period:
            return None
            
        # Calculate moving averages
        import numpy as np
        fast_ma = np.mean(closes[-self.fast_period:])
        slow_ma = np.mean(closes[-self.slow_period:])
        prev_fast_ma = np.mean(closes[-self.fast_period-1:-1])
        prev_slow_ma = np.mean(closes[-self.slow_period-1:-1])
        
        # Detect crossover
        if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
            # Bullish crossover - BUY
            return {
                "symbol": self.symbol,
                "action": "buy",
                "quantity": self.quantity,
                "price": current_prices[self.symbol],
                "reason": f"MA crossover: {fast_ma:.2f} > {slow_ma:.2f}"
            }
        
        elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
            # Bearish crossover - SELL
            # Check if we have positions to sell
            return {
                "symbol": self.symbol,
                "action": "sell",
                "quantity": self.quantity,
                "price": current_prices[self.symbol],
                "reason": f"MA crossunder: {fast_ma:.2f} < {slow_ma:.2f}"
            }
        
        return None  # No crossover
```

---

### Accessing Historical Data

Strategies can access historical data via the Data API:

```python
def generate_signal(self, team, bars, current_prices):
    # Access the data API
    data_api = team['api']
    
    # Get last 100 minute bars for AAPL
    df = data_api.getLastN('AAPL', 100)
    # Returns: DataFrame with columns [timestamp, open, high, low, close, volume]
    
    # Get specific date range
    from datetime import datetime, timedelta
    start = datetime.now() - timedelta(days=7)
    end = datetime.now()
    df = data_api.getRange('AAPL', start, end)
    
    # Get today's data
    from datetime import date
    df = data_api.getDay('AAPL', date.today())
    
    # Use the data
    returns = df['close'].pct_change()
    volatility = returns.std()
    
    # Your logic...
```

---

## Data Flow

### Market Data Pipeline

```
Alpaca Markets
     ↓
┌────────────────┐
│ Ticker Adapter │ ← Fetches minute bars
└────────┬───────┘
         ↓
┌────────────────┐
│  Caching Layer │ ← In-memory cache (60s TTL)
└────────┬───────┘
         ↓
┌────────────────┐
│ Parquet Writer │ ← Persists to disk
└────────┬───────┘
         ↓
data/prices/minute_bars/
  └── y=2025/m=10/d=10/
      └── minute_bars-2025-10-10.parquet
```

**Cache behavior:**
- First fetch: ~500ms (Alpaca API)
- Subsequent fetches (same minute): ~1ms (cache hit)
- Cache invalidation: Every minute boundary

---

### Trade Data Pipeline

```
Strategy Signal
     ↓
┌────────────────┐
│ Trade Executor │ ← Validates & executes
└────────┬───────┘
         ↓
┌────────────────┐
│ Alpaca Broker  │ ← Submits order
└────────┬───────┘
         ↓
┌────────────────┐
│ Portfolio      │ ← Updates positions
└────────┬───────┘
         ↓
┌────────────────┐
│ JSONL Writer   │ ← Real-time logging
└────────┬───────┘
         ↓
data/team/{team_id}/
  ├── trades.jsonl        ← Append-only log
  └── portfolio/
      └── 2025-10-10.jsonl ← Minute snapshots
```

---

### Metrics Calculation Pipeline

```
Portfolio Snapshots (JSONL/Parquet)
     ↓
┌────────────────────────┐
│ Performance Calculator │
└────────┬───────────────┘
         ↓
    Calculate:
    - Returns
    - Volatility
    - Sharpe Ratio
    - Sortino Ratio
    - Calmar Ratio
    - Drawdowns
    - Win Rate
    - Profit Factor
         ↓
┌────────────────────────┐
│  Metrics JSONL         │ ← Store results
└────────────────────────┘
         ↓
┌────────────────────────┐
│  API Cache             │ ← Serve via API
└────────────────────────┘
```

**Calculation frequency:**
- On-demand via API (no pre-calculation)
- Cached for 60 seconds
- Recalculated when data changes

---

## Performance & Metrics

### Available Metrics

For full details, see `API_DOCUMENTATION.md`. Key metrics:

| Metric | Description | Formula |
|--------|-------------|---------|
| **Sharpe Ratio** | Risk-adjusted return | (Return - RiskFree) / Volatility |
| **Sortino Ratio** | Downside risk-adjusted return | Return / Downside Volatility |
| **Calmar Ratio** | Return vs max drawdown | Annualized Return / Max Drawdown |
| **Max Drawdown** | Worst peak-to-trough decline | (Trough - Peak) / Peak |
| **Total Return** | Overall profit/loss | (End - Start) / Start |
| **Win Rate** | Profitable periods percentage | Wins / Total Periods |
| **Profit Factor** | Wins vs losses ratio | Total Gains / Total Losses |

### Calculation Details

**Returns:**
- Calculated as: `(value[t] - value[t-1]) / value[t-1]`
- Filtered to remove invalid values (inf, nan)
- Annualized using: 252 trading days × 390 minutes/day

**Volatility:**
- Standard deviation of returns
- Annualized: `std * sqrt(252 * 390)`

**Edge Cases:**
- Zero volatility → Returns `null` (JSON-safe)
- Zero drawdown → Calmar ratio = `null`
- No losses → Profit factor = `null`
- All handled gracefully, no crashes

---

## API Reference

### Quick Reference

**Public Endpoints (No Auth):**
```
GET  /leaderboard                    # Current rankings
GET  /api/v1/leaderboard/history     # Historical data
GET  /api/v1/leaderboard/metrics     # With performance metrics
GET  /activity/recent                # Activity log
GET  /activity/stream                # SSE stream
```

**Team Endpoints (Require API Key):**
```
GET  /line/{team_key}                # Team status (JSON)
GET  /{team_key}                     # Team status (text)
GET  /api/v1/team/{id}/history       # Historical data
GET  /api/v1/team/{id}/metrics       # Performance metrics
GET  /api/v1/team/{id}/trades        # Trade history
```

For complete API documentation, see `API_DOCUMENTATION.md`.

---

## FAQ - Frequently Asked Questions

### General Questions

#### Q: What are the rate limits on the API?

**A:** Currently, there are **NO rate limits** implemented on the QTC Alpha API.

**Recommended limits (when implemented):**
- Public leaderboard: 60 requests/minute
- Historical data: 30 requests/minute
- Metrics endpoints: 20 requests/minute
- Team-specific: 100 requests/hour

**Note:** Rate limiting will be added in a future update using SlowAPI.

---

#### Q: What are the Alpaca API rate limits?

**A:** Alpaca has the following rate limits:

**Market Data API:**
- **200 requests/minute** per API key
- **Data delays:** Real-time for paid, 15-min delayed for free

**Trading API:**
- **200 requests/minute** for orders
- **Unlimited** for account/position queries

**Our mitigation:**
- ✅ Data caching (60s TTL) reduces API calls
- ✅ Batch requests when possible
- ✅ Single fetch per minute for all symbols
- ✅ Result: ~1-2 Alpaca API calls per minute (well under limit)

**Reference:** https://alpaca.markets/docs/api-references/market-data-api/#rate-limit

---

#### Q: What is the latency for trade execution?

**A:** End-to-end latency breakdown:

| Step | Latency | Notes |
|------|---------|-------|
| Market data fetch | 300-800ms | Alpaca API call |
| Strategy execution | 10-50ms | Per strategy |
| Signal validation | 5-10ms | Local checks |
| Order submission | 100-300ms | Alpaca API call |
| Order fill | 50-500ms | Market conditions |
| **Total** | **~500ms-2s** | Per trade |

**Factors affecting latency:**
- Network latency to Alpaca (typically 20-50ms)
- Market liquidity (low volume = slower fills)
- Time of day (market open = slower)
- Order type (market = fast, limit = variable)

**Optimization:**
- Use market orders for speed
- Trade liquid stocks (high volume)
- Avoid market open/close (high volatility)

---

#### Q: How often do strategies run?

**A:** Strategies execute **every minute** during market hours.

**Schedule:**
- **Market Hours:** 9:30 AM - 4:00 PM ET (Monday-Friday)
- **Frequency:** Every minute (:00, :01, :02, ... :59)
- **Total:** ~390 executions per day
- **Yearly:** ~98,280 executions (252 trading days)

**Non-market hours:**
- Strategies do NOT run
- System idles or performs maintenance
- Data consolidation (JSONL → Parquet)

---

#### Q: Can I run strategies 24/7 (crypto)?

**A:** Currently **NO**, but planned for future.

**Current limitation:**
- Only US equity market hours (9:30 AM - 4:00 PM ET)
- Controlled by `market_hours.py`

**To enable 24/7:**
1. Set `run_24_7: true` in `team_registry.yaml`
2. Use crypto symbols (BTCUSD, ETHUSD)
3. Modify market hours check

**Coming soon:** Native crypto support.

---

#### Q: What symbols can I trade?

**A:** Defined in `TICKER_UNIVERSE` (app/config/settings.py):

**Default universe:**
- Major stocks: AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META
- Indices: SPY, QQQ, DIA
- Crypto: BTCUSD, ETHUSD (if enabled)

**To add symbols:**
```python
# In settings.py
TICKER_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "YOUR_SYMBOL_HERE"
]
```

**Restrictions:**
- Must be supported by Alpaca
- Must have sufficient liquidity
- No OTC/penny stocks (risk management)

---

#### Q: What's the maximum position size?

**A:** Currently **no hard limit**, but:

**Risk management:**
- Teams start with $100,000 initial capital
- Cannot spend more than available cash
- Cannot sell more than owned shares
- No margin/leverage (cash account only)

**Recommended limits:**
- Max 20% of portfolio per position
- Max 10 positions at once
- Max 5% trade size per minute

**To enforce limits:**
Add validation in `trade_executor.py`

---

#### Q: Can strategies communicate with each other?

**A:** **NO** - Strategies are isolated.

**Security model:**
- Each strategy runs in its own namespace
- No shared memory
- No inter-process communication
- No file access
- No network access

**Why:**
- Prevent collusion between teams
- Security isolation
- Fair competition

---

#### Q: How is P&L calculated?

**A:** Two methods:

**1. Realized P&L (closed positions):**
```python
realized_pl = (sell_price - avg_buy_price) * quantity
```

**2. Unrealized P&L (open positions):**
```python
unrealized_pl = (current_price - avg_cost) * quantity
```

**Total P&L:**
```python
total_pl = realized_pl + unrealized_pl
```

**Portfolio value:**
```python
market_value = cash + sum(position.value for all positions)
```

---

#### Q: Are there trading fees?

**A:** Depends on your Alpaca account:

**Alpaca Paper Trading:** FREE
- No commission
- No fees
- Unlimited trades

**Alpaca Live Trading:**
- **$0 commission** on stocks/ETFs
- **SEC fees:** ~$0.0000278 per dollar sold (negligible)
- **Example:** Sell $10,000 → $0.28 fee

**Our system:**
- Does NOT automatically deduct fees from portfolio
- Fees reflected in Alpaca account balance
- Fetch real account balance periodically

---

### Technical Questions

#### Q: What happens if my strategy times out?

**A:** Timeout = 5 seconds per strategy

**Behavior:**
1. Strategy execution is killed
2. No trade submitted that minute
3. Error logged to `qtc_alpha_errors.log`
4. System continues with other teams

**Prevention:**
- Optimize your code
- Avoid heavy computations
- Cache calculations
- Use vectorized operations (NumPy)

---

#### Q: What happens if Alpaca is down?

**A:** Graceful degradation:

**If market data fails:**
1. Uses cached data (last successful fetch)
2. Continues with stale data
3. Logs warning
4. Retries next minute

**If order submission fails:**
1. Portfolio updated locally (optimistic update)
2. Order NOT submitted to broker
3. Error logged
4. Retry on next signal

**If prolonged outage:**
- System continues running
- All trades logged locally
- Manual reconciliation may be needed

---

#### Q: How do I debug my strategy?

**A:** Several options:

**1. Local testing:**
```python
# test_strategy.py
from external_strategies.myteam.strategy import Strategy

strategy = Strategy()
signal = strategy.generate_signal(
    team={"id": "test", "cash": 100000},
    bars={"AAPL": {"close": [150.0, 150.5]}},
    current_prices={"AAPL": 150.5}
)
print(signal)
```

**2. Check logs:**
```bash
# View errors
tail -f /opt/qtc/qtc_alpha_errors.log

# View general logs
tail -f /opt/qtc/qtc_alpha.log
```

**3. Check trade history:**
```bash
# View recent trades
tail /opt/qtc/data/team/yourteam/trades.jsonl | jq
```

**4. Use print statements:**
```python
# In strategy.py (shows in logs)
import sys
print(f"Debug: MA crossover detected", file=sys.stderr)
```

---

#### Q: Can I use machine learning models?

**A:** **Limited** - with restrictions:

**Allowed:**
- ✅ NumPy/Pandas operations
- ✅ SciPy statistical functions
- ✅ Pre-calculated features

**NOT allowed:**
- ❌ TensorFlow/PyTorch (not in allowed imports)
- ❌ External API calls for predictions
- ❌ Loading models from files
- ❌ Training models in real-time (too slow)

**Workaround:**
- Train model offline
- Convert to NumPy operations
- Implement inference logic in strategy

**Example:**
```python
# Pre-trained linear regression coefficients
class MLStrategy:
    def __init__(self):
        self.weights = np.array([0.5, -0.3, 0.8])  # Trained offline
        
    def generate_signal(self, team, bars, current_prices):
        # Extract features
        features = self.extract_features(bars)
        # Predict
        prediction = np.dot(features, self.weights)
        # Trade based on prediction
        if prediction > 0.5:
            return {"symbol": "AAPL", "action": "buy", ...}
```

---

#### Q: How is data stored and how much space does it use?

**A:** Storage breakdown:

**Per team per day:**
- Trades: ~1-10 KB (depends on # trades)
- Portfolio snapshots: ~150-500 KB (390 minutes × ~500 bytes)
- Metrics: ~50-100 KB
- **Total:** ~200-600 KB/day

**After Parquet conversion:**
- Portfolio: ~50-100 KB/day (70-80% compression)
- Cumulative: ~20-30 MB/year per team

**Market data (shared):**
- Minute bars: ~5-10 MB/day (for 20 symbols)
- Yearly: ~2-3 GB (compressed Parquet)

**Total system (10 teams):**
- Daily: ~10-20 MB
- Monthly: ~300-600 MB
- Yearly: ~4-7 GB

**Storage recommendations:**
- Minimum: 50 GB
- Recommended: 200 GB
- Archive old data to S3/GCS after 1 year

---

#### Q: Can I backtest my strategy?

**A:** **Not built-in**, but possible:

**Option 1: Manual backtest**
```python
# backtest.py
from external_strategies.myteam.strategy import Strategy
import pandas as pd

# Load historical data
df = pd.read_parquet('data/prices/minute_bars/...')

strategy = Strategy()
portfolio_value = 100000
cash = 100000

for i in range(len(df)):
    # Prepare data
    bars = prepare_bars(df.iloc[:i])
    prices = {"AAPL": df.iloc[i]['close']}
    
    # Generate signal
    signal = strategy.generate_signal(
        {"id": "test", "cash": cash},
        bars,
        prices
    )
    
    # Simulate trade
    if signal:
        if signal['action'] == 'buy':
            cash -= signal['quantity'] * signal['price']
        # etc...
    
print(f"Final value: ${portfolio_value}")
```

**Option 2: Use external tools**
- Backtrader
- Zipline
- QuantConnect

**Coming soon:** Built-in backtesting module

---

### Security & Compliance

#### Q: Is my strategy code private?

**A:** **YES** - Strategies are private.

**Security measures:**
- Each team's code stored separately
- No cross-team access
- Not exposed via API
- Only admins have file system access

**Intellectual property:**
- You own your code
- Platform cannot use/share your strategies
- No reverse engineering by competitors

---

#### Q: Is real money at risk?

**A:** Depends on configuration:

**Paper Trading (default):**
- Virtual money ($100k starting)
- Real market prices
- Real order execution (simulated)
- **NO REAL MONEY AT RISK**

**Live Trading (opt-in):**
- Real money
- Real trades
- Real profits/losses
- **RISK WARNING:** You can lose money

**Recommendation:**
- Start with paper trading
- Test thoroughly
- Understand risks before going live

---

#### Q: What security measures are in place?

**A:** Multiple layers:

**1. Code isolation:**
- Sandboxed execution
- No system access
- No network access
- Timeout enforcement

**2. API security:**
- API key authentication
- Team isolation
- (Future) Rate limiting
- (Future) IP whitelisting

**3. Trade validation:**
- Balance checks
- Position limits
- Price reasonableness
- Market hours enforcement

**4. Data security:**
- Team data isolated
- No cross-team queries
- File system permissions
- Encrypted API keys (recommended)

---

## Troubleshooting

### Common Issues

#### Issue: "Strategy not loading"

**Symptoms:** Strategy doesn't execute, no trades

**Causes:**
1. Syntax error in strategy.py
2. Missing `Strategy` class
3. Missing `generate_signal()` method
4. Security validation failure

**Solution:**
```bash
# Check logs
tail -f qtc_alpha_errors.log

# Test strategy locally
python -c "from external_strategies.myteam.strategy import Strategy; s = Strategy()"

# Validate security
python -m app.loaders.static_check external_strategies/myteam
```

---

#### Issue: "No trades executing"

**Possible causes:**
1. Outside market hours
2. Strategy returning `None`
3. Insufficient cash
4. Alpaca credentials missing

**Debug:**
```python
# Add debug output to strategy
def generate_signal(self, team, bars, current_prices):
    import sys
    print(f"Cash: {team['cash']}", file=sys.stderr)
    print(f"Bars: {list(bars.keys())}", file=sys.stderr)
    # ... rest of code
```

---

#### Issue: "API returns 401 Unauthorized"

**Cause:** Invalid API key

**Solution:**
```bash
# Check your API key
cat data/api_keys.json

# Test authentication
curl "http://localhost:8000/api/v1/team/yourteam/metrics?key=YOUR_KEY"
```

---

#### Issue: "Metrics show null values"

**Cause:** This is **normal** for some metrics

**When `null` is expected:**
- Sharpe ratio when volatility = 0
- Calmar ratio when drawdown = 0
- Profit factor when no losses

**See:** `EDGE_CASES_FIXED.md` for details

---

#### Issue: "High latency / slow responses"

**Causes:**
1. Large time range requested
2. Too many data points
3. Many teams competing
4. Alpaca API slow

**Solutions:**
```python
# Limit data points
GET /api/v1/team/{id}/history?days=1&limit=500  # Instead of days=30

# Use caching
# Responses are cached for 60s

# Check Alpaca status
curl https://status.alpaca.markets/
```

---

## Deployment Guide

### Production Deployment

**1. System requirements:**
```
OS: Ubuntu 20.04+ or similar
CPU: 2+ cores
RAM: 4 GB minimum, 8 GB recommended
Disk: 50 GB minimum, 200 GB recommended
Python: 3.12+
```

**2. Install dependencies:**
```bash
cd /opt/qtc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Configure environment:**
```bash
# Create .env file
cat > .env << EOF
QTC_ENV=production
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
ALPACA_PAPER=true
ADMIN_API_KEY=$(openssl rand -hex 32)
EOF

# Load environment
source .env
```

**4. Start services:**

**Option A: Manual**
```bash
# Terminal 1: Orchestrator
python -m app.main --env production

# Terminal 2: API Server
uvicorn app.api.server:app --host 0.0.0.0 --port 8000
```

**Option B: Systemd (recommended)**
```bash
# Create service files
sudo cp deployment/qtc-orchestrator.service /etc/systemd/system/
sudo cp deployment/qtc-api.service /etc/systemd/system/

# Start services
sudo systemctl enable qtc-orchestrator qtc-api
sudo systemctl start qtc-orchestrator qtc-api

# Check status
sudo systemctl status qtc-orchestrator
```

**5. Configure Nginx (optional):**
```nginx
server {
    listen 80;
    server_name api.qtcq.xyz;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**6. Monitoring:**
```bash
# Watch logs
tail -f qtc_alpha.log
tail -f qtc_alpha_errors.log

# Monitor resource usage
htop

# Check disk usage
df -h
```

---

### Scaling Considerations

**For 10-50 teams:**
- Single server sufficient
- 4 GB RAM
- 2 CPU cores

**For 50-100 teams:**
- 8 GB RAM
- 4 CPU cores
- SSD recommended

**For 100+ teams:**
- Consider horizontal scaling
- Separate API and orchestrator servers
- Redis for caching
- PostgreSQL for metrics
- Load balancer

---

## Additional Resources

### Documentation Files

- `README.md` - Quick start guide
- `API_DOCUMENTATION.md` - Complete API reference
- `SYSTEM_DOCUMENTATION.md` - This file
- `strategy_starter/README.md` - Strategy development guide

### Logs

- `qtc_alpha.log` - General system log
- `qtc_alpha_errors.log` - Error log
- Team-specific: `data/team/{id}/trades.jsonl`

### External Links

- Alpaca API Docs: https://alpaca.markets/docs/
- Alpaca Status: https://status.alpaca.markets/
- FastAPI Docs: https://fastapi.tiangolo.com/

---

## Support & Contributing

### Getting Help

1. Check this documentation
2. Review logs
3. Check GitHub issues
4. Contact admin

### Reporting Bugs

Include:
- Error message
- Steps to reproduce
- Log excerpts
- System info

### Contributing

Contributions welcome! Areas:
- Strategy examples
- Documentation improvements
- Bug fixes
- Feature requests

---

## Changelog

### Version 1.0 (October 2025)
- ✅ Initial release
- ✅ Minute-based trading
- ✅ Alpaca integration
- ✅ REST API
- ✅ Performance metrics
- ✅ Security sandboxing

### Upcoming Features
- 🔄 Rate limiting
- 🔄 Backtesting module
- 🔄 Crypto support (24/7)
- 🔄 Web-based strategy editor
- 🔄 Real-time dashboard
- 🔄 Mobile app

---

**Last Updated:** October 10, 2025  
**Version:** 1.0  
**Maintainer:** QTC Alpha Team

