# QTC Alpha Trader Handbook

This comprehensive guide walks you through building and delivering production-ready strategies for the QTC Alpha trading orchestrator. You'll learn how to request data, construct compliant orders, monitor performance, and deploy strategies through the web dashboard.

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Strategy Interface](#2-strategy-interface)
3. [Data Access Methods](#3-data-access-methods)
4. [Order Construction](#4-order-construction)
5. [API Endpoints Reference](#5-api-endpoints-reference)
6. [Strategy Upload & Management](#6-strategy-upload--management)
7. [Performance Monitoring](#7-performance-monitoring)
8. [Error Handling & Debugging](#8-error-handling--debugging)
9. [Best Practices](#9-best-practices)
10. [Deployment Checklist](#10-deployment-checklist)

## 1. Getting Started

### 1.1 Your Starting Point

- Start with `macd_strategy.py` in this starter kit - a complete MACD implementation
- The orchestrator imports your strategy class, instantiates it once, and calls `generate_signal(team, bars, current_prices)` once per minute
- Return a trade dict when you want to submit an order; return `None` to skip the minute
- Your strategy runs in a sandboxed environment with access to historical data and real-time prices

### 1.2 Strategy Class Structure

```python
class Strategy:
    def __init__(self, **kwargs):
        # Initialize your strategy parameters
        # Access team-specific parameters via kwargs
        pass

    def generate_signal(self, team, bars, current_prices):
        # Your trading logic here
        # Return None or a valid signal dict
        return None
```

### 1.3 Web Dashboard Access

- **Login**: Use your team API key to access the web dashboard
- **Dashboard URL**: `https://your-domain.com/dashboard?key=YOUR_API_KEY`
- **Features**: Real-time portfolio monitoring, trade history, performance metrics, strategy upload
- **API Key**: Generated automatically when your team is created - check with operations team

## 2. Strategy Interface

### 2.1 Input Parameters

Your `generate_signal` method receives three parameters:

#### `team` - Team State Object
```python
{
    "id": "team-alpha",           # Team slug/identifier
    "name": "Alpha Team",          # Display name
    "cash": 10000.50,             # Available cash
    "positions": {                 # Current positions
        "AAPL": {
            "quantity": 100.0,
            "avg_cost": 150.25,
            "side": "buy"
        }
    },
    "params": {                   # Team-specific parameters
        "risk_level": "medium",
        "max_position_size": 0.1
    },
    "api": StrategyDataAPI()       # Data access helper
}
```

#### `bars` - Historical Minute Bars
```python
{
    "AAPL": {
        "timestamp": ["2025-01-15T09:30:00+00:00", "2025-01-15T09:31:00+00:00"],
        "open": [150.25, 150.30],
        "high": [150.50, 150.45],
        "low": [150.20, 150.25],
        "close": [150.45, 150.40],
        "volume": [1000000, 950000]
    }
}
```

#### `current_prices` - Latest Prices
```python
{
    "AAPL": 150.40,
    "NVDA": 425.75,
    "SPY": 485.20
}
```

### 2.2 Strategy Parameters

Access team-specific parameters through the `team["params"]` dictionary:

```python
def __init__(self, **kwargs):
    # Default parameters
    self.symbol = kwargs.get("symbol", "AAPL")
    self.quantity = kwargs.get("quantity", 10)
    self.risk_level = kwargs.get("risk_level", "medium")
    
    # Strategy-specific parameters
    self.fast_period = kwargs.get("fast_period", 12)
    self.slow_period = kwargs.get("slow_period", 26)
    self.signal_period = kwargs.get("signal_period", 9)
```

## 3. Data Access Methods

### 3.1 Local Data Access (Strategy Runtime)

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

# Multi-symbol queries (more efficient)
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

### 3.2 API Data Access (External Tools)

For external applications, dashboards, or analysis tools, use these REST API endpoints:

#### Get Historical Data by Time Range
```bash
GET /api/v1/market/bars?symbols=AAPL&start=2025-01-15T09:30:00&end=2025-01-15T16:00:00&key=YOUR_KEY
```

**Multi-Symbol Example:**
```bash
GET /api/v1/market/bars?symbols=AAPL,SPY,NVDA&start=2025-10-15T09:30:00&end=2025-10-16T16:00:00&key=YOUR_KEY
```

**Response:**
```json
{
    "symbol": "AAPL",
    "start": "2025-01-15T09:30:00+00:00",
    "end": "2025-01-15T16:00:00+00:00",
    "bar_count": 2340,
    "bars": [
        {
            "timestamp": "2025-01-15T09:30:00+00:00",
            "open": 225.50,
            "high": 226.00,
            "low": 225.30,
            "close": 225.80,
            "volume": 1250000
        }
    ]
}
```

### 3.3 Data Quality and Reliability

**Automatic Data Repair:**
- The system automatically scans for missing data every 15 minutes during market hours (9:30 AM - 4:00 PM ET)
- During off-hours, scans occur every 60 minutes
- All data operations are idempotent (no duplication or overwriting)
- Data is stored in partitioned parquet files (one file per day)

**Data Sources:**
- **Equity symbols**: Alpaca Markets via IEX feed (NYSE/NASDAQ)
- **Crypto symbols**: Alpaca Crypto (BTC, ETH, etc.)
- **Trading hours**: US equity market hours for stocks, 24/7 for crypto
- **Data Feed**: IEX (Investors Exchange) - ensures consistent pricing from single exchange

**Data Format:**
- All timestamps are in UTC
- Prices are in USD
- Volume and trade count may be null for some symbols
- Data is automatically backfilled when gaps are detected

## 4. Order Construction

### 4.1 Signal Validation

Signals must validate against `StrategySignal`, which enforces:

| Field | Type | Notes |
|-------|------|-------|
| `symbol` | `str` | Must match a ticker the orchestrator can trade |
| `action` | `"buy"` or `"sell"` | Use `"sell"` for both selling long and entering shorts |
| `quantity` | `float` (positive) | Shares to buy/sell; fractional OK |
| `price` | `float` (positive) | Your target price (limit-style). Use latest price for market-like behavior |
| `confidence` | `float`, optional | Optional score between 0 and 1 (no enforcement) |
| `reason` | `str`, optional | Short explanation shown in logs |

### 4.2 Building Signals

Use the provided helper (recommended) or return a plain dict:

```python
from macd_strategy import make_signal

def generate_signal(self, team, bars, current_prices):
    symbol = "NVDA"
    price = float(current_prices.get(symbol) or bars[symbol]["close"][-1])
    
    return make_signal(
        symbol=symbol,
        action="buy",
        quantity=5,
        price=price,
        confidence=0.7,
        reason="MACD bullish crossover"
    )
```

### 4.3 Order Types and Execution

**Supported Order Types:**
- `market`: Execute at current market price
- `limit`: Execute only at specified price or better

**Time in Force:**
- `day`: Valid for the current trading day
- `gtc`: Good till cancelled
- `ioc`: Immediate or cancel
- `fok`: Fill or kill

**Tips:**
- Always guard against missing data (`bars.get(symbol)` may be `None` right after market open)
- Never return negative or zero quantities/prices; they will fail validation
- Return `None` to skip placing an order on a given minute
- Use `current_prices` for real-time execution, historical data for analysis

## 5. API Endpoints Reference

### 5.1 Team Management Endpoints

#### Get Team Status
```bash
GET /api/v1/team/{team_id}?key=YOUR_KEY
```
Returns current portfolio value, positions, cash, and basic metrics.

#### Get Team History
```bash
GET /api/v1/team/{team_id}/history?key=YOUR_KEY&days=7&limit=1000
```
Returns portfolio value history over specified time period.

#### Get Team Trades
```bash
GET /api/v1/team/{team_id}/trades?key=YOUR_KEY&limit=100
```
Returns recent trade history with execution details.

#### Get Team Metrics
```bash
GET /api/v1/team/{team_id}/metrics?key=YOUR_KEY&days=30
```
Returns comprehensive performance metrics including Sharpe ratio, drawdown, win rate.

#### Get Team Positions Summary
```bash
GET /api/v1/team/{team_id}/positions/summary?key=YOUR_KEY
```
Returns current positions with P&L and performance data.

#### Get Position History for Specific Symbol
```bash
GET /api/v1/team/{team_id}/position/{symbol}/history?key=YOUR_KEY&days=7&limit=1000
```
Returns historical position data for a specific symbol.

### 5.2 Order Management Endpoints

#### Get Open Orders
```bash
GET /api/v1/team/{team_id}/orders/open?key=YOUR_KEY
```
Returns all pending orders.

#### Get Order Details
```bash
GET /api/v1/team/{team_id}/orders/{order_id}?key=YOUR_KEY
```
Returns detailed information about a specific order.

#### Cancel Order
```bash
DELETE /api/v1/team/{team_id}/orders/{order_id}?key=YOUR_KEY
```
Cancels a pending order.

### 5.3 Strategy Upload Endpoints

#### Upload Single Strategy File
```bash
POST /api/v1/team/{team_id}/upload-strategy
Content-Type: multipart/form-data

key=YOUR_KEY
file=@strategy.py
```

#### Upload Strategy Package (ZIP)
```bash
POST /api/v1/team/{team_id}/upload-strategy-package
Content-Type: multipart/form-data

key=YOUR_KEY
file=@strategy_package.zip
```

#### Upload Multiple Files
```bash
POST /api/v1/team/{team_id}/upload-multiple-files
Content-Type: multipart/form-data

key=YOUR_KEY
files=@strategy.py
files=@indicators.py
files=@config.py
```

### 5.4 Market Data Endpoints

#### Get Historical Bars
```bash
GET /api/v1/market/bars?symbols=AAPL&start=2025-01-15T09:30:00&end=2025-01-15T16:00:00&key=YOUR_KEY
```

#### Get Available Symbols
```bash
GET /api/v1/market/symbols?key=YOUR_KEY
```

### 5.5 System Status Endpoints

#### Get System Status
```bash
GET /api/v1/status
```
Returns system health, market status, and orchestrator information.

#### Get Data Repair Status
```bash
GET /api/v1/data-repair/status
```
Returns data repair service status and statistics.

### 5.6 Leaderboard Endpoints

#### Get Current Leaderboard
```bash
GET /leaderboard
```
Returns current portfolio values for all teams (public).

#### Get Leaderboard with Metrics
```bash
GET /api/v1/leaderboard/metrics?days=30&sort_by=sharpe_ratio
```
Returns comprehensive performance metrics for all teams.

#### Get Leaderboard History
```bash
GET /api/v1/leaderboard/history?days=7&limit=500
```
Returns historical portfolio values for all teams.

### 5.7 Monitoring Endpoints

#### Get Team Errors
```bash
GET /api/v1/team/{team_id}/errors?key=YOUR_KEY&limit=50
```
Returns recent error logs for your strategy.

#### Get Execution Health
```bash
GET /api/v1/team/{team_id}/execution-health?key=YOUR_KEY
```
Returns strategy execution statistics and health metrics.

#### Get Recent Activity
```bash
GET /activity/recent?limit=100
```
Returns recent system activity (public).

#### Stream Activity (Server-Sent Events)
```bash
GET /activity/stream
```
Real-time activity stream (public).

### 5.8 Simple Status Endpoint

#### Team Heartbeat
```bash
GET /{team_key}
```
Returns simple text status for your team (public, no authentication required).

## 6. Strategy Upload & Management

### 6.1 Web Dashboard Upload

1. **Login**: Access the dashboard with your API key
2. **Upload**: Use the file upload interface to submit your strategy
3. **Validation**: System automatically validates your strategy
4. **Deployment**: Strategy is deployed on the next trading cycle

### 6.2 Repository Management

#### Daily Refresh System
- **Automatic Sync**: Every night at 1:00 AM UTC, the system pulls the latest commit from your repository
- **Entry Point**: Specify your strategy class via `entry_point: "strategy:Strategy"`
- **Branch Support**: Default branch is `main`, but you can specify any branch or tag
- **SHA Tracking**: System tracks commits to avoid unnecessary updates

#### Repository Structure
```
your-strategy-repo/
├── strategy.py          # Main strategy file (required)
├── indicators.py         # Technical indicators
├── config.py            # Configuration
├── requirements.txt      # Dependencies (optional)
└── README.md            # Documentation
```

#### Team Registry Configuration
```yaml
teams:
  - team_id: "team-alpha"
    name: "Alpha Team"
    git_url: "https://github.com/your-org/alpha-strategy.git"
    branch: "main"
    entry_point: "strategy:Strategy"
    initial_cash: 10000
    run_24_7: false
    params:
      risk_level: "medium"
      max_position_size: 0.1
```

### 6.3 Strategy Validation

The system performs automatic validation:

1. **Syntax Check**: Python syntax validation
2. **Import Test**: Ensures all imports are available
3. **Interface Test**: Calls `generate_signal` with dummy data
4. **Dependency Check**: Validates `requirements.txt` against allowed packages

### 6.4 Allowed Dependencies

Only whitelisted packages are permitted for security:
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `scipy` - Scientific computing
- `ta-lib` - Technical analysis
- `requests` - HTTP requests (limited)

## 7. Performance Monitoring

### 7.1 Key Metrics

**Portfolio Metrics:**
- `portfolio_value`: Current total portfolio value
- `total_return_percentage`: Total return since inception
- `annualized_return_percentage`: Annualized return rate
- `max_drawdown_percentage`: Maximum peak-to-trough decline

**Risk Metrics:**
- `sharpe_ratio`: Risk-adjusted return measure
- `sortino_ratio`: Downside risk-adjusted return
- `calmar_ratio`: Return to max drawdown ratio
- `volatility_percentage`: Portfolio volatility

**Trading Metrics:**
- `win_rate_percentage`: Percentage of profitable trades
- `profit_factor`: Gross profit / Gross loss ratio
- `avg_trade_return`: Average return per trade
- `total_trades`: Total number of trades executed

### 7.2 Real-time Monitoring

**Dashboard Features:**
- Live portfolio value updates
- Real-time position tracking
- Trade execution monitoring
- Performance chart visualization
- Error log viewing

**API Monitoring:**
```python
# Get current performance
response = requests.get(f"/api/v1/team/{team_id}/metrics?key={api_key}")
metrics = response.json()

# Monitor in real-time
while True:
    status = requests.get(f"/api/v1/team/{team_id}?key={api_key}")
    print(f"Portfolio: ${status.json()['portfolio_value']:.2f}")
    time.sleep(60)  # Update every minute
```

### 7.3 Performance Tracking

The system automatically tracks:
- Portfolio value snapshots every minute
- Trade execution details
- Position changes
- Error occurrences
- Strategy execution timing

## 8. Error Handling & Debugging

### 8.1 Error Types

**Strategy Errors:**
- `ValidationError`: Invalid signal format
- `DataError`: Missing or invalid data
- `ExecutionError`: Order execution failure
- `ImportError`: Missing dependencies

**System Errors:**
- `NetworkError`: Data feed connectivity issues
- `RateLimitError`: API rate limit exceeded
- `AuthenticationError`: Invalid API key

### 8.2 Error Handling Best Practices

```python
def generate_signal(self, team, bars, current_prices):
    try:
        # Your strategy logic
        api = team["api"]
        
        # Safe data access
        if not bars.get("AAPL"):
            return None
            
        recent_data = api.getLastN("AAPL", 60)
        if recent_data.empty:
            return None
            
        # Process data safely
        latest_price = recent_data["close"].iloc[-1]
        
        # Generate signal
        return make_signal(
            symbol="AAPL",
            action="buy",
            quantity=10,
            price=latest_price,
            reason="Strategy signal"
        )
        
    except Exception as e:
        # Log error but don't crash
        print(f"Strategy error: {e}")
        return None
```

### 8.3 Debugging Tools

**Error Logs:**
```bash
GET /api/v1/team/{team_id}/errors?key=YOUR_KEY&limit=50
```

**Execution Health:**
```bash
GET /api/v1/team/{team_id}/execution-health?key=YOUR_KEY
```

**Local Testing:**
```bash
python -m app.main --teams "demo-team;./your-strategy;strategy:Strategy;100000" --duration 5
```

## 9. Best Practices

### 9.1 Strategy Development

**Data Handling:**
- Always check for empty DataFrames before processing
- Use `current_prices` for real-time execution
- Use historical data for analysis and indicators
- Handle missing data gracefully

**Performance:**
- Use batch queries (`getRangeMulti`) for multiple symbols
- Cache expensive calculations in `__init__`
- Avoid blocking operations in `generate_signal`
- Keep signal generation under 1 second

**Risk Management:**
- Implement position sizing based on portfolio value
- Set maximum position limits
- Use stop-losses and take-profits
- Monitor drawdown and adjust accordingly

### 9.2 Code Organization

**File Structure:**
```python
# strategy.py - Main strategy logic
class Strategy:
    def __init__(self, **kwargs):
        self.indicators = TechnicalIndicators()
        self.risk_manager = RiskManager()
        
    def generate_signal(self, team, bars, current_prices):
        # Main strategy logic
        pass

# indicators.py - Technical indicators
class TechnicalIndicators:
    def macd(self, data):
        # MACD calculation
        pass

# risk_manager.py - Risk management
class RiskManager:
    def calculate_position_size(self, signal, portfolio):
        # Position sizing logic
        pass
```

### 9.3 Testing Strategy

**Local Testing:**
```bash
# Test with dummy data
python -m app.main --teams "test-team;./strategy;strategy:Strategy;10000" --duration 10

# Test with specific parameters
python -m app.main --teams "test-team;./strategy;strategy:Strategy;10000" --duration 5
```

**Validation Checklist:**
- [ ] Strategy returns valid signals or `None`
- [ ] No blocking operations in `generate_signal`
- [ ] Proper error handling for missing data
- [ ] Reasonable position sizes
- [ ] All dependencies are whitelisted

## 10. Deployment Checklist

### 10.1 Pre-Deployment

- [ ] Strategy validates locally with dummy data
- [ ] All imports are from allowed packages
- [ ] Error handling is implemented
- [ ] Position sizing is reasonable
- [ ] Strategy parameters are configurable

### 10.2 Repository Setup

- [ ] Repository is public or accessible to service account
- [ ] `strategy.py` contains your main strategy class
- [ ] `requirements.txt` lists only allowed dependencies
- [ ] Entry point is correctly specified
- [ ] Branch/tag is specified if not `main`

### 10.3 Team Configuration

- [ ] Team is added to `team_registry.yaml`
- [ ] API key is generated and provided
- [ ] Initial cash amount is set
- [ ] Strategy parameters are configured
- [ ] `run_24_7` setting is appropriate

### 10.4 Post-Deployment

- [ ] Strategy loads without errors
- [ ] Portfolio value updates correctly
- [ ] Trades execute as expected
- [ ] Performance metrics are reasonable
- [ ] Error logs are clean

### 10.5 Monitoring

- [ ] Dashboard access works with API key
- [ ] Real-time monitoring is functional
- [ ] Performance metrics are tracked
- [ ] Error notifications are set up
- [ ] Daily sync is working

## 11. Advanced Features

### 11.1 Multi-Symbol Strategies

```python
def generate_signal(self, team, bars, current_prices):
    signals = []
    
    # Process multiple symbols
    for symbol in ["AAPL", "NVDA", "SPY"]:
        if symbol in bars and symbol in current_prices:
            signal = self._analyze_symbol(symbol, bars[symbol], current_prices[symbol])
            if signal:
                signals.append(signal)
    
    # Return first signal (or implement portfolio-level logic)
    return signals[0] if signals else None
```

### 11.2 Portfolio-Level Risk Management

```python
def calculate_position_size(self, signal, team):
    portfolio_value = team["cash"] + sum(
        pos["quantity"] * pos["avg_cost"] 
        for pos in team["positions"].values()
    )
    
    # Risk-based position sizing
    risk_per_trade = portfolio_value * 0.02  # 2% risk per trade
    position_size = risk_per_trade / signal["price"]
    
    return min(position_size, signal["quantity"])
```

### 11.3 State Management

```python
class Strategy:
    def __init__(self, **kwargs):
        self.state = {
            "last_signal": None,
            "signal_count": 0,
            "last_trade_time": None
        }
    
    def generate_signal(self, team, bars, current_prices):
        # Update state
        self.state["signal_count"] += 1
        
        # Use state in decision making
        if self.state["last_signal"] == "buy":
            return self._generate_sell_signal(team, bars, current_prices)
        else:
            return self._generate_buy_signal(team, bars, current_prices)
```

## 12. Troubleshooting

### 12.1 Common Issues

**Strategy Not Loading:**
- Check Python syntax
- Verify all imports are available
- Ensure `generate_signal` method exists
- Check entry point specification

**No Trades Executing:**
- Verify signal format is correct
- Check for data availability
- Ensure prices are positive
- Review error logs

**Performance Issues:**
- Monitor execution time
- Check for blocking operations
- Optimize data access patterns
- Review memory usage

### 12.2 Support Resources

- **Documentation**: This handbook and API documentation
- **Error Logs**: Available via API endpoints
- **Dashboard**: Real-time monitoring and debugging
- **Operations Team**: Contact for deployment issues

---

## Quick Reference

### Signal Helper Function
```python
def make_signal(symbol, action, quantity, price, confidence=None, reason=None):
    return {
        "symbol": symbol,
        "action": action,  # "buy" or "sell"
        "quantity": quantity,
        "price": price,
        "confidence": confidence,
        "reason": reason
    }
```

### Essential API Endpoints
```bash
# Team status
GET /api/v1/team/{team_id}?key=YOUR_KEY

# Upload strategy
POST /api/v1/team/{team_id}/upload-strategy

# Get trades
GET /api/v1/team/{team_id}/trades?key=YOUR_KEY

# System status
GET /api/v1/status
```

### Data Access Methods
```python
api = team["api"]
recent = api.getLastN("AAPL", 60)           # Last 60 minutes
day = api.getDay("AAPL", date.today())      # Today's data
range_data = api.getRange("AAPL", start, end)  # Custom range
```

Remember: The system automatically handles data repair, strategy refresh, and error recovery. Focus on building robust, well-tested strategies that handle edge cases gracefully.
