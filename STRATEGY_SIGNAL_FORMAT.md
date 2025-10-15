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
- Stock ticker symbol
- Examples: `"AAPL"`, `"GOOGL"`, `"TSLA"`, `"BTC"` (for crypto)
- Must be in the configured ticker universe

### `action` (string)  
- Trading direction
- Values: `"buy"` or `"sell"`

### `quantity` (number)
- Number of shares to trade
- Supports fractional shares (e.g., `10.5`, `0.1`)
- Must be positive
- Examples: `10`, `5.5`, `0.25`

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
- **Cons:** May not execute if price doesn't reach limit
- **Use when:** Price is critical and you can wait for execution

```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.00,        # Will only buy at $150.00 or LESS
    "order_type": "limit",
    "time_in_force": "gtc"  # Keep trying until filled
}
```

### `time_in_force` (string)
- **Default:** `"day"`
- **Values:** `"day"`, `"gtc"`, `"ioc"`, `"fok"`

#### Time in Force Options

| Value | Name | Behavior |
|-------|------|----------|
| `"day"` | Day Order | Valid until end of trading day (default) |
| `"gtc"` | Good-Til-Canceled | Remains active until filled or manually canceled |
| `"ioc"` | Immediate-Or-Cancel | Fill immediately or cancel unfilled portion |
| `"fok"` | Fill-Or-Kill | Fill entire order immediately or cancel completely |

**Examples:**

```python
# Intraday strategy - cancel at end of day
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.00,
    "order_type": "limit",
    "time_in_force": "day"  # Cancels at market close
}

# Position entry - wait for good price
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 100,
    "price": 145.00,
    "order_type": "limit",
    "time_in_force": "gtc"  # Stays active across days
}

# Quick scalp - immediate execution only
return {
    "symbol": "AAPL",
    "action": "sell",
    "quantity": 10,
    "price": 151.00,
    "order_type": "limit",
    "time_in_force": "ioc"  # Cancel if not immediate
}
```

---

## Complete Examples

### Example 1: Simple Market Order
```python
def generate_signal(self, team, bars, current_prices):
    if self.should_buy():
        return {
            "symbol": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": current_prices["AAPL"]
            # order_type defaults to "market"
            # time_in_force defaults to "day"
        }
    return None
```

### Example 2: Limit Order with Good-Til-Canceled
```python
def generate_signal(self, team, bars, current_prices):
    current_price = current_prices["GOOGL"]
    
    # Buy at 5% discount
    limit_price = current_price * 0.95
    
    return {
        "symbol": "GOOGL",
        "action": "buy",
        "quantity": 5,
        "price": limit_price,
        "order_type": "limit",
        "time_in_force": "gtc"  # Keep order active
    }
```

### Example 3: Conditional Order Type
```python
def generate_signal(self, team, bars, current_prices):
    volatility = self.calculate_volatility(bars["TSLA"])
    
    # Use limit orders in high volatility
    order_type = "limit" if volatility > 0.05 else "market"
    
    return {
        "symbol": "TSLA",
        "action": "sell",
        "quantity": 10,
        "price": current_prices["TSLA"],
        "order_type": order_type
    }
```

---

## Execution Details

### Execution Price
- **Market orders**: Platform retrieves actual filled price from Alpaca
- **Limit orders**: May not fill immediately; execution price retrieved when filled
- **Local-only mode** (no Alpaca): Uses requested price as execution price

### Trade Record
All executed trades are logged with:
- `requested_price`: Price you specified
- `execution_price`: Actual filled price (may differ for market orders)
- `order_type`: Type of order placed
- `broker_order_id`: Alpaca order ID (null in local-only mode)

### Accessing via API
```bash
curl "http://localhost:8000/api/v1/team/YOUR_TEAM/trades?key=YOUR_API_KEY"
```

Returns:
```json
{
  "team_id": "your_team",
  "count": 1,
  "trades": [
    {
      "timestamp": "2025-10-15T14:30:00Z",
      "symbol": "AAPL",
      "side": "buy",
      "quantity": 10,
      "requested_price": 150.50,
      "execution_price": 150.52,
      "order_type": "market",
      "broker_order_id": "abc-123-alpaca-id"
    }
  ]
}
```

---

## Best Practices

### 1. Choose Order Type Wisely
- **Use market orders** when timing is critical
- **Use limit orders** when price is critical
- Consider volatility and liquidity

### 2. Set Appropriate Prices
- **Market orders**: Use current price as reference
- **Limit orders**: Set realistic limits based on support/resistance levels

### 3. Manage Time in Force
- **Intraday strategies**: Use `"day"` to avoid overnight exposure
- **Swing strategies**: Use `"gtc"` carefully, monitor open orders
- **High-frequency**: Use `"ioc"` or `"fok"` for immediate execution

### 4. Handle Partial Fills
- Limit orders may partially fill
- Check position sizes in next cycle
- Adjust quantities accordingly

### 5. Test in Paper Mode
- Always test new order types in paper trading first
- Verify execution behavior matches expectations
- Monitor for unexpected fills or cancellations

---

## Migration from Old Format

### Before (deprecated)
```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.0,
    "confidence": 0.8,  # No longer used
    "reason": "optional"  # No longer used
}
```

### After (current)
```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.0,
    "order_type": "market",  # New: specify order type
    "time_in_force": "day"   # New: specify duration
}
```

**Note:** The old format still works (defaults to market/day), but `confidence` and `reason` fields are ignored.

---

## Error Handling

### Invalid Signals
The platform validates all signals. Common errors:

```python
# ❌ Missing required field
return {"symbol": "AAPL", "action": "buy"}  # Missing quantity, price

# ❌ Invalid order type
return {"symbol": "AAPL", "action": "buy", "quantity": 10, 
        "price": 150, "order_type": "stop"}  # "stop" not yet supported

# ❌ Invalid time in force
return {"symbol": "AAPL", "action": "buy", "quantity": 10,
        "price": 150, "time_in_force": "invalid"}

# ✅ Valid signal
return {"symbol": "AAPL", "action": "buy", "quantity": 10, "price": 150}
```

### Order Failures
- Market closed: Order rejected immediately
- Insufficient funds: Order rejected
- Alpaca API error: Order rejected, error logged
- Invalid symbol: Order rejected

Check `/api/v1/team/{team_id}/errors` endpoint for error details.

---

**Last Updated:** October 15, 2025
**See Also:** [ALPACA_INTEGRATION.md](ALPACA_INTEGRATION.md), [README.md](README.md)

