# QTC Alpha Starter Kit

This starter kit provides everything you need to build and deploy trading strategies for the QTC Alpha trading system.

## Contents

### 📚 Documentation
- **`TRADER_HANDBOOK.md`** - Comprehensive guide covering all aspects of strategy development, API usage, and deployment
- **`README.md`** - This file with quick start instructions

### 🚀 Strategy Examples
- **`macd_strategy.py`** - Complete MACD (Moving Average Convergence Divergence) strategy with:
  - Technical indicator calculations
  - Risk management
  - Error handling
  - Configurable parameters
  - State tracking
- **`simple_strategy.py`** - Basic alternating buy/sell strategy demonstrating the minimum required interface

### 🔧 Helper Functions
Both strategy files include the `make_signal()` helper function for creating valid trading signals.

## Quick Start

### 1. Choose Your Starting Point

**For beginners:**
Start with `simple_strategy.py` to understand the basic interface.

**For advanced users:**
Use `macd_strategy.py` as a template for building sophisticated strategies.

### 2. Local Testing

Test your strategy locally before deployment:

```bash
# Test with simple strategy
python -m app.main --teams "demo-team;./starter_kit;strategy:Strategy;100000" --duration 5

# Test with MACD strategy
python -m app.main --teams "demo-team;./starter_kit;macd_strategy:Strategy;100000" --duration 5
```

### 3. Customize Your Strategy

Edit the strategy file to:
- Change target symbols
- Adjust parameters
- Implement your trading logic
- Add risk management

### 4. Deploy Your Strategy

**Option A: Web Dashboard**
1. Login with your API key
2. Upload your strategy files
3. Monitor performance in real-time

**Option B: Repository**
1. Push your strategy to a Git repository
2. Provide repository URL to operations team
3. Strategy will sync automatically

## Strategy Interface

Every strategy must implement this interface:

```python
class Strategy:
    def __init__(self, **kwargs):
        # Initialize your strategy
        pass
    
    def generate_signal(self, team, bars, current_prices):
        # Return trading signal or None
        return None
```

### Input Parameters

- **`team`**: Team state (cash, positions, API access)
- **`bars`**: Historical minute bars data
- **`current_prices`**: Latest prices for all symbols

### Output

Return a signal dictionary or `None`:

```python
{
    "symbol": "AAPL",
    "action": "buy",  # or "sell"
    "quantity": 10,
    "price": 150.25,
    "confidence": 0.8,  # optional
    "reason": "MACD bullish crossover"  # optional
}
```

## Key Features

### Data Access
```python
api = team["api"]
recent = api.getLastN("AAPL", 60)      # Last 60 minutes
day = api.getDay("AAPL", date.today()) # Today's data
range_data = api.getRange("AAPL", start, end)  # Custom range
```

### Risk Management
```python
# Position sizing based on portfolio value
portfolio_value = team["cash"] + sum(pos["quantity"] * pos["avg_cost"] for pos in team["positions"].values())
max_position_value = portfolio_value * 0.1  # 10% max position
```

### Error Handling
```python
try:
    # Your strategy logic
    return signal
except Exception as e:
    print(f"Strategy error: {e}")
    return None
```

## API Endpoints

### Team Management
- `GET /api/v1/team/{team_id}?key=YOUR_KEY` - Team status
- `GET /api/v1/team/{team_id}/trades?key=YOUR_KEY` - Trade history
- `GET /api/v1/team/{team_id}/metrics?key=YOUR_KEY` - Performance metrics

### Strategy Upload
- `POST /api/v1/team/{team_id}/upload-strategy` - Upload single file
- `POST /api/v1/team/{team_id}/upload-multiple-files` - Upload multiple files

### Market Data
- `GET /api/v1/market/bars?symbols=AAPL&start=...&end=...&key=YOUR_KEY` - Historical data

### System Status
- `GET /api/v1/status` - System health
- `GET /leaderboard` - Public leaderboard

## Best Practices

### 1. Data Validation
```python
if not bars.get("AAPL"):
    return None

recent_data = api.getLastN("AAPL", 60)
if recent_data.empty:
    return None
```

### 2. Position Sizing
```python
def calculate_position_size(self, signal, team):
    portfolio_value = team["cash"] + sum(
        pos["quantity"] * pos["avg_cost"] 
        for pos in team["positions"].values()
    )
    max_position_value = portfolio_value * 0.1  # 10% max
    return min(signal["quantity"], max_position_value / signal["price"])
```

### 3. State Management
```python
def __init__(self, **kwargs):
    self.last_signal = None
    self.position_entry_price = None
    self.signal_count = 0
```

### 4. Error Recovery
```python
def generate_signal(self, team, bars, current_prices):
    try:
        # Strategy logic
        return signal
    except Exception as e:
        print(f"Error: {e}")
        return None
```

## Deployment Checklist

- [ ] Strategy validates locally
- [ ] All imports are from allowed packages
- [ ] Error handling is implemented
- [ ] Position sizing is reasonable
- [ ] Repository is accessible
- [ ] API key is available
- [ ] Team is configured in registry

## Support

- **Documentation**: See `TRADER_HANDBOOK.md` for complete reference
- **Examples**: Study `macd_strategy.py` for advanced patterns
- **API Reference**: All endpoints documented in the handbook
- **Dashboard**: Monitor performance in real-time

## Next Steps

1. **Read the Handbook**: Start with `TRADER_HANDBOOK.md`
2. **Study Examples**: Understand `macd_strategy.py`
3. **Test Locally**: Use the provided test commands
4. **Deploy**: Upload via dashboard or repository
5. **Monitor**: Track performance and iterate

Happy trading! 🚀
