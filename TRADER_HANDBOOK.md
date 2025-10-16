# Trader Handbook

This guide walks you through building and delivering your first production-ready strategy for the QTC orchestrator. You will start from `example_strat.py`, learn how to request data, construct compliant orders, and verify that everything is wired up through the API.

## 1. Know Your Starting Point
- `example_strat.py` buys and sells `NVDA` every other minute. It exists purely to demonstrate the interface; do not trade it.
- The orchestrator imports your strategy class, instantiates it once, and calls `generate_signal(team, bars, current_prices)` once per minute.
- Return a trade dict when you want to submit an order; return `None` to skip the minute.

```python
class Strategy:
    def __init__(self, **kwargs):
        ...

    def generate_signal(self, team, bars, current_prices):
        # your logic here
        return None  # or a signal dict built as shown below
```

## 2. Understand the Inputs You Receive
- `team`: lightweight state about your account.
  - Keys: `id` (team slug), `name`, `cash`, `positions`, `params`, and `api`.
  - `params` carries any overrides configured for your team.
- `bars`: minute bars keyed by symbol.
  - Example: `{"AAPL": {"timestamp": [...], "open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]}}`.
  - Bars contain the most recent window the orchestrator has pulled (typically the last trading day plus the current session).
- `current_prices`: latest price per symbol. Use this for mark-to-market logic; fall back to `bars[symbol]["close"][-1]` if needed.

## 3. Data Access Methods

### 3.1 Local Data Access (When Strategy Runs on Server)

Historical data is available via the helper attached at `team["api"]`:

```python
api = team["api"]

# Get recent data (last N minutes)
recent = api.getLastN("NVDA", 120)                  # last 120 minutes

# Get data for a specific day
day = api.getDay("NVDA", date(2025, 1, 15))         # full trading day

# Get data for a time range
start_dt = datetime(2025, 1, 15, 9, 30, tzinfo=timezone.utc)
end_dt = datetime(2025, 1, 15, 16, 0, tzinfo=timezone.utc)
window = api.getRange("NVDA", start_dt, end_dt)

# Multi-symbol queries
symbols = ["AAPL", "NVDA", "SPY"]
multi_data = api.getRangeMulti(symbols, start_dt, end_dt)
multi_day = api.getDayMulti(symbols, date(2025, 1, 15))
multi_recent = api.getLastNMulti(symbols, 60)
```

**Data Format:** All methods return pandas DataFrames with columns:
- `ticker`: Symbol (e.g., "AAPL")
- `timestamp`: Minute timestamp (UTC)
- `open`, `high`, `low`, `close`: OHLC prices
- `volume`: Trading volume (if available)
- `trade_count`: Number of trades (if available)
- `vwap`: Volume-weighted average price (if available)

### 3.2 API Data Access (External Access)

For external applications, dashboards, or analysis tools, use these REST API endpoints:

#### Get Historical Data by Time Range
```bash
GET /api/v1/market-data/{symbol}/range?start=2025-01-15T09:30:00Z&end=2025-01-15T16:00:00Z
```

**Example:**
```bash
curl "https://your-domain.com/api/v1/market-data/AAPL/range?start=2025-01-15T09:30:00Z&end=2025-01-15T16:00:00Z"
```

**Response:**
```json
{
  "symbol": "AAPL",
  "start": "2025-01-15T09:30:00+00:00",
  "end": "2025-01-15T16:00:00+00:00",
  "data_points": 390,
  "data": [
    {
      "timestamp": "2025-01-15T09:30:00+00:00",
      "open": 150.25,
      "high": 150.50,
      "low": 150.20,
      "close": 150.45,
      "volume": 1000000,
      "trade_count": 5000,
      "vwap": 150.35
    }
  ]
}
```

#### Get Data for Specific Day
```bash
GET /api/v1/market-data/{symbol}/day/{date}
```

**Example:**
```bash
curl "https://your-domain.com/api/v1/market-data/AAPL/day/2025-01-15"
```

#### Get Recent Data
```bash
GET /api/v1/market-data/{symbol}/recent/{count}
```

**Example:**
```bash
curl "https://your-domain.com/api/v1/market-data/AAPL/recent/100"
```

#### Get Available Symbols
```bash
GET /api/v1/market-data/symbols
```

**Response:**
```json
{
  "symbols": ["AAPL", "NVDA", "SPY", "QQQ", "BTC", "ETH"],
  "count": 6,
  "equity_symbols": ["AAPL", "NVDA", "SPY", "QQQ"],
  "crypto_symbols": ["BTC", "ETH"]
}
```

#### Check Data Repair Status
```bash
GET /api/v1/data-repair/status
```

**Response:**
```json
{
  "running": true,
  "last_repair_time": "2025-01-15T15:45:00+00:00",
  "root_path": "data/prices/minute_bars",
  "symbols_tracked": 25,
  "market_hours": true,
  "next_repair_in_minutes": 12
}
```

### 3.3 Data Quality and Reliability

**Automatic Data Repair:**
- The system automatically scans for missing data every 15 minutes during market hours (9:30 AM - 4:00 PM ET)
- During off-hours, scans occur every 60 minutes
- All data operations are idempotent (no duplication or overwriting)
- Data is stored in partitioned parquet files (one file per day)

**Data Sources:**
- **Equity symbols**: Alpaca Markets (NYSE/NASDAQ)
- **Crypto symbols**: Alpaca Crypto (BTC, ETH, etc.)
- **Trading hours**: US equity market hours for stocks, 24/7 for crypto

**Data Format:**
- All timestamps are in UTC
- Prices are in USD
- Volume and trade count may be null for some symbols
- Data is automatically backfilled when gaps are detected

## 4. Constructing a Valid Order
Signals must validate against `StrategySignal`, which enforces:

| Field | Type | Notes |
|-------|------|-------|
| `symbol` | `str` | Must match a ticker the orchestrator can trade. |
| `action` | `"buy"` or `"sell"` | Use `"sell"` for both selling long and entering shorts. |
| `quantity` | `float` (positive) | Shares to buy/sell; fractional OK. |
| `price` | `float` (positive) | Your target price (limit-style). Use the latest price if you want market-like behaviour. |
| `confidence` | `float`, optional | Optional score between 0 and 1 (no enforcement). |
| `reason` | `str`, optional | Short explanation shown in logs. |

Build signals with the provided helper (recommended) or return a plain dict with the same shape:

```python
from example_strat import make_signal

def generate_signal(...):
    symbol = "NVDA"
    price = float(current_prices.get(symbol) or bars[symbol]["close"][-1])
    return make_signal(
        symbol=symbol,
        action="buy",
        quantity=5,
        price=price,
        confidence=0.7,
        reason="Momentum crossover"
    )
```

Tips:
- Always guard against missing data (`bars.get(symbol)` may be `None` right after market open).
- Never return negative or zero quantities/prices; they will fail validation.
- Return `None` to skip placing an order on a given minute.

## 5. Local Testing Workflow
1. Copy `example_strat.py` into your own repo and rename the class or file if you prefer.
2. Run the orchestrator pointing at your strategy:
   ```bash
   python -m app.main --teams "demo-team;./path-to-your-repo;strategy:Strategy;100000" --duration 5
   ```
   This runs for five minutes, feeds your `generate_signal`, and prints any validation errors.
3. Check generated artifacts under `data/team/<team_slug>/` for trades and portfolio snapshots.

## 6. Monitoring via the API (Team Slug Required)
Your team slug is the `team_id` we register (for example, `team-alpha`). You will also receive an API key. Use these to inspect results:

```bash
# Plain-text heartbeat
curl "https://your-domain.com/line/team-alpha?key=YOUR_KEY"

# Detailed JSON snapshot + metrics
curl "https://your-domain.com/api/v1/team/team-alpha?key=YOUR_KEY" | jq

# Portfolio history for the last 7 days
curl "https://your-domain.com/api/v1/team/team-alpha/history?key=YOUR_KEY&days=7" | jq

# Recent trades
curl "https://your-domain.com/api/v1/team/team-alpha/trades?key=YOUR_KEY&limit=50" | jq

# Open orders
curl "https://your-domain.com/api/v1/team/team-alpha/orders/open?key=YOUR_KEY" | jq
```

If you just need the public leaderboard (no key required):

```bash
curl "https://your-domain.com/leaderboard" | jq
```

## 7. Delivering Your Strategy Repo
1. **Repository layout**
   - Place your strategy class in a Python file (for example `strategy.py`) and expose it via an entry point string like `strategy:Strategy`.
   - Ensure `__init__.py` is present if you organise code into packages.
   - Include a lightweight `requirements.txt` if you depend on third-party libraries (only allow-listed packages are permitted).
2. **Naming**
   - Keep the repository name aligned with your team slug when possible (e.g., `team-alpha-strategy`).
   - Match the entry point we configure in `team_registry.yaml` (`entry_point: strategy:Strategy` by default). If you change the class name or file name, tell us so we can update the entry point.
3. **Access**
   - Host the repo on GitHub (public or grant read access to our service account). SSH URLs are fine; HTTPS is preferred.
   - Branch default is `main`. If you want us to pull a different branch or a tag, let us know.
4. **Submission**
   - Send us the repo URL, branch (or tag/SHA), and confirm the entry point string.
   - Optional: provide a short README describing your strategy parameters so the operations team can double-check configuration.

## 8. How the Automation Picks Up Your Code
- Nightly sync: every evening the orchestrator runs `sync_all_from_registry`, which shallow-clones the latest commit for each team listed in `team_registry.yaml`.
- If the SHA has not changed since the previous sync, we skip cloning and keep the existing copy.
- After syncing, the loader instantiates your strategy and runs a quick dry-run with dummy data to ensure `generate_signal` validates. If that fails, we quarantine the repo and notify you.
- During trading hours, we call your class every minute; any exceptions are logged but will not stop other teams.

## 9. Data Access Best Practices

### 9.1 Performance Considerations
- **Local access** (via `team["api"]`) is fastest - use for real-time strategy logic
- **API access** is slower but more flexible - use for external tools and analysis
- **Batch queries** are more efficient than individual requests
- **Recent data** (`getLastN`) is faster than historical data (`getRange`)

### 9.2 Error Handling
```python
def generate_signal(self, team, bars, current_prices):
    api = team["api"]
    
    try:
        # Get recent data with error handling
        recent_data = api.getLastN("AAPL", 60)
        if recent_data.empty:
            logger.warning("No recent data for AAPL")
            return None
            
        # Process data safely
        latest_price = recent_data["close"].iloc[-1]
        # ... your logic here
        
    except Exception as e:
        logger.error(f"Error accessing data: {e}")
        return None
```

### 9.3 Data Validation
- Always check if DataFrames are empty before processing
- Validate timestamps are in expected ranges
- Handle missing volume/trade_count data gracefully
- Use `current_prices` for real-time prices, historical data for analysis

## 10. Checklist Before You Ship
- Strategy returns either `None` or a valid signal dict each minute.
- No blocking network or file writes; stay within the allowed imports.
- You have sensible defaults for quantities and prices.
- Repo builds cleanly with your `requirements.txt`.
- You supplied: repo URL, branch/tag, entry point, and team slug.
- **Data access is properly handled with error checking**
- **Strategy gracefully handles missing or incomplete data**

Once we add you to `team_registry.yaml`, the nightly pull will fetch your latest commit, and your logic will run automatically in production the next morning.
