# Strategy Signal Format

This document describes the format for trading signals returned by strategies.

---

## Signal Structure

Strategies implement `generate_signal(team, bars, current_prices)` which returns a dictionary (or `None` for no action).

### Basic Example
```python
def generate_signal(self, team, bars, current_prices):
    # Your strategy logic here
    return {
        "symbol": "AAPL",
        "action": "buy",
        "quantity": 10,
        "price": 150.50,
        "order_type": "market",      # Optional, defaults to "market"
        "time_in_force": "day"       # Optional, defaults to "day"
    }
```

---

## Required Fields

### `symbol` (string)
- Stock ticker symbol or cryptocurrency symbol
- Examples: `"AAPL"`, `"GOOGL"`, `"TSLA"`, `"BTC"` (for crypto)
- **Crypto symbols are automatically converted**: `"BTC"` → `"BTC/USD"`
- Must be in the configured ticker universe

### `action` (string)  
- Trading direction
- Values: `"buy"` or `"sell"`

### `quantity` (number)
- Number of shares or crypto units to trade
- Supports fractional shares and crypto amounts (e.g., `10.5`, `0.1`, `0.5`)
- Must be positive
- Examples: `10`, `5.5`, `0.25`, `0.1` (for crypto)

### `price` (number)
- Meaning depends on order type:
  - **Market orders**: Reference price (actual execution may vary)
  - **Limit orders**: Limit price (will only execute at this price or better)
- Examples: `150.50`, `1234.56`

---

## Optional Fields

### `order_type` (string)
- **Default:** `"market"`
- **Values:** `"market"` or `"limit"`

#### Market Orders (`"market"`)
- Execute immediately at current market price
- **Pros:** Guaranteed execution (when market is open)
- **Cons:** Price may differ from requested price due to slippage
- **Use when:** You need immediate execution and price is less critical

```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.50,        # Reference price only
    "order_type": "market"  # Executes immediately
}
```

#### Limit Orders (`"limit"`)
- Execute only at specified price or better
- **Pros:** Price control, no negative slippage
- **Cons:** Execution not guaranteed
- **Use when:** Price is critical and you can wait for execution

```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.00,           # Will only buy at $150.00 or less
    "order_type": "limit",
    "time_in_force": "gtc"     # Keep order active until filled
}
```

### Crypto Trading Examples

#### Crypto Market Order
```python
return {
    "symbol": "BTC",           # Automatically converted to BTC/USD
    "action": "buy",
    "quantity": 0.1,           # Fractional crypto amounts supported
    "price": 50000.00,        # Reference price
    "order_type": "market"     # Executes immediately at market price
}
```

#### Crypto Limit Order
```python
return {
    "symbol": "ETH",           # Automatically converted to ETH/USD
    "action": "sell",
    "quantity": 0.5,
    "price": 3000.00,         # Will only sell at $3000.00 or higher
    "order_type": "limit",
    "time_in_force": "gtc"     # Good until cancelled (24/7 crypto trading)
}
```

## Crypto Trading Features

### Automatic Symbol Conversion
- Crypto symbols are automatically converted to Alpaca format
- `"BTC"` → `"BTC/USD"`, `"ETH"` → `"ETH/USD"`, etc.
- No manual symbol formatting required

### 24/7 Trading Support
- Crypto markets trade 24/7 (unlike stock markets)
- Market hours validation automatically allows crypto trading at any time
- Crypto orders use `GTC` (Good Until Cancelled) by default for better 24/7 execution

### Fractional Trading
- Both stocks and crypto support fractional quantities
- Examples: `0.1 BTC`, `0.5 ETH`, `10.5 AAPL`
- Quantities passed as strings to preserve decimal precision

---

## Complete Examples

### Stock Trading
```python
def generate_signal(self, team, bars, current_prices):
    return {
        "symbol": "AAPL",
        "action": "buy",
        "quantity": 10,
        "price": 150.50,
        "order_type": "market"
    }
```

### Crypto Trading
```python
def generate_signal(self, team, bars, current_prices):
    return {
        "symbol": "BTC",        # Automatically converted to BTC/USD
        "action": "buy",
        "quantity": 0.1,        # Fractional crypto amounts
        "price": 50000.00,
        "order_type": "limit",
        "time_in_force": "gtc"  # Good for 24/7 crypto trading
    }
```

### Mixed Portfolio Strategy
```python
def generate_signal(self, team, bars, current_prices):
    # Can trade both stocks and crypto in the same strategy
    if some_condition:
        return {
            "symbol": "AAPL",
            "action": "buy",
            "quantity": 5,
            "price": current_prices.get("AAPL", 150),
            "order_type": "market"
        }
    elif another_condition:
        return {
            "symbol": "ETH",
            "action": "sell",
            "quantity": 0.5,
            "price": current_prices.get("ETH", 3000),
            "order_type": "limit"
        }
    return None  # No trade
```

---

## Error Handling

If you encounter issues with crypto trading:

1. **Check symbol format**: Use base symbols like `"BTC"`, not `"BTC/USD"`
2. **Verify market hours**: Crypto trades 24/7, but ensure your strategy handles this
3. **Fractional quantities**: Use decimal numbers like `0.1`, not integers like `1`
4. **Order types**: Market orders execute immediately, limit orders wait for price

---

## References

- [Alpaca Crypto Trading Documentation](https://docs.alpaca.markets/docs/crypto-trading-1)
- [Strategy Development Guide](starter_kit/README.md)
- [Complete API Documentation](API_DOCUMENTATION.md)