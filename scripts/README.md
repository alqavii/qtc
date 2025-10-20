# Scripts Directory

This directory contains utility scripts for the QTC Alpha trading system.

## Scripts

### `run_strategies.py`

A utility script for testing trading strategies in isolation. This script:

- Fetches market data (or uses mock data if Alpaca credentials are not available)
- Runs multiple example strategies in parallel using ProcessPoolExecutor
- Demonstrates the expected strategy signal format
- Can be used for strategy development and testing

#### Usage

```bash
# From the project root
python scripts/run_strategies.py

# Or from the scripts directory
cd scripts
python run_strategies.py
```

#### Strategy Signal Format

Strategies should return a dictionary with the following format:

```python
{
    "symbol": "AAPL",        # Ticker symbol (supports both stocks and crypto)
    "action": "buy",         # "buy" or "sell"
    "quantity": 10,          # Number of shares/units
    "price": 150.0,          # Reference price
    "confidence": 0.8,       # Optional confidence score
    "reason": "optional"     # Optional reason for the trade
}
```

#### Features

- **Parallel Execution**: Strategies run in separate processes for isolation
- **Timeout Handling**: Strategies that take too long are terminated
- **Error Handling**: Graceful handling of strategy errors
- **Mock Data**: Works without Alpaca credentials using sample data
- **Crypto Support**: Supports both stock and cryptocurrency symbols

#### Example Output

```
Warning: Could not fetch real data (You must supply a method of authentication)
Using mock data for testing...
All outputs:
Team1 -> {'symbol': 'AAPL', 'action': 'buy', 'quantity': 10, 'price': 150.0, 'confidence': 0.8, 'reason': 'optional'}
Team2 -> {'symbol': 'AAPL', 'action': 'sell', 'quantity': 10, 'price': 150.0, 'confidence': 0.8, 'reason': 'optional'}
Team3 -> {'symbol': 'AAPL', 'action': 'buy', 'quantity': 10, 'price': 150.0, 'confidence': 0.8, 'reason': 'optional'}
```

## Adding New Scripts

When adding new utility scripts to this directory:

1. Follow the same import pattern as `run_strategies.py`:
   ```python
   import sys
   from pathlib import Path
   sys.path.append(str(Path(__file__).parent.parent))
   ```

2. Handle missing dependencies gracefully (like Alpaca credentials)

3. Add documentation to this README

4. Use descriptive filenames that indicate the script's purpose

