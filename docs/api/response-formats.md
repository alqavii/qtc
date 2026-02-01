# API Response Format Reference

**Quick reference for frontend developers**  
**Last Updated:** October 15, 2025

This document describes the **actual** response formats returned by the QTC Alpha API, not what you might expect. All responses have been verified against the live API.

---

## Trades Endpoint

### `/api/v1/team/{team_id}/trades`

**Actual Response Structure:**

```json
{
  "team_id": "admin",
  "count": 52,
  "trades": [
    {
      "team_id": "admin",
      "timestamp": "2025-10-15 14:51:00.420460+00:00",
      "symbol": "NVDA",
      "side": "sell",
      "quantity": "1.0",
      "requested_price": "182.55",
      "execution_price": "182.55",
      "order_type": "market",
      "broker_order_id": "2ed2d1b4-8278-40c2-bb24-4a56f3dc13f4"
    }
  ]
}
```

### Field Mapping for Frontend:

| Frontend Needs | API Provides | How to Get It |
|---------------|--------------|---------------|
| `price` | `execution_price` | `parseFloat(trade.execution_price)` |
| `total_value` | **NOT PROVIDED** | Calculate: `parseFloat(trade.quantity) * parseFloat(trade.execution_price)` |
| `position_after` | **NOT PROVIDED** | Track cumulatively or use `/portfolio-history` endpoint |

### JavaScript Example:

```javascript
// Transform API response for frontend
const transformTrade = (trade) => ({
  timestamp: trade.timestamp,
  symbol: trade.symbol,
  side: trade.side,
  quantity: parseFloat(trade.quantity),
  price: parseFloat(trade.execution_price),
  totalValue: parseFloat(trade.quantity) * parseFloat(trade.execution_price),
  requestedPrice: parseFloat(trade.requested_price),
  orderType: trade.order_type,
  brokerOrderId: trade.broker_order_id
});

// Usage
fetch(`${API_BASE}/api/v1/team/admin/trades?key=${API_KEY}&limit=20`)
  .then(res => res.json())
  .then(data => {
    const trades = data.trades.map(transformTrade);
    displayTrades(trades);
  });
```

---

## Important Data Type Notes

### All Numeric Values are Strings

The API returns numeric values as **strings** to preserve decimal precision. You MUST parse them:

```javascript
// ❌ WRONG - Will fail
trade.quantity + trade.execution_price  // "1.0182.55" (string concatenation!)

// ✅ CORRECT
parseFloat(trade.quantity) * parseFloat(trade.execution_price)  // 182.55
```

### Timestamp Formats

Timestamps come in two formats:

**Format 1:** `"2025-10-15 14:51:00.420460+00:00"` (space separator)  
**Format 2:** `"2025-10-15T14:51:00.420460+00:00"` (T separator)

Parse both with:
```javascript
new Date(trade.timestamp)  // Works for both formats
```

---

## Position Tracking

The `/trades` endpoint does **NOT** include position information. To get positions:

### Option 1: Use Portfolio Snapshot Endpoint

```bash
GET /api/v1/team/{team_id}?key={api_key}
```

Returns current positions in the `snapshot.positions` field.

### Option 2: Calculate Cumulative Position

Track position yourself from trades:

```javascript
let position = 0;
trades.forEach(trade => {
  const qty = parseFloat(trade.quantity);
  if (trade.side === 'buy') {
    position += qty;
  } else {
    position -= qty;
  }
  trade.position_after = position;
});
```

### Option 3: Use Portfolio History Endpoint (if implemented)

```bash
GET /api/v1/team/{team_id}/portfolio-history?key={api_key}
```

Returns full snapshots with positions at each timestamp.

---

## Complete Field Reference

### Trade Object Fields

| Field | Type | Example | Always Present? | Notes |
|-------|------|---------|----------------|-------|
| `team_id` | string | "admin" | ✅ Yes | Team identifier |
| `timestamp` | string | "2025-10-15 14:51:00+00:00" | ✅ Yes | ISO 8601 UTC |
| `symbol` | string | "NVDA" | ✅ Yes | Stock ticker |
| `side` | string | "buy" or "sell" | ✅ Yes | Trade direction |
| `quantity` | string | "10.0" | ✅ Yes | Number of shares |
| `requested_price` | string | "182.55" | ✅ Yes | Strategy requested price |
| `execution_price` | string | "182.55" | ✅ Yes | Actual execution price |
| `order_type` | string | "market" | ✅ Yes | Order type |
| `broker_order_id` | string or null | "uuid..." | ⚠️ Maybe | Present if executed via broker |

---

## Frontend Integration Examples

### React Component Example:

```javascript
function TradesTable({ teamId, apiKey }) {
  const [trades, setTrades] = useState([]);
  
  useEffect(() => {
    fetch(`https://api.qtcq.xyz/api/v1/team/${teamId}/trades?key=${apiKey}&limit=50`)
      .then(res => res.json())
      .then(data => {
        const formatted = data.trades.map(t => ({
          timestamp: new Date(t.timestamp),
          symbol: t.symbol,
          side: t.side,
          quantity: parseFloat(t.quantity),
          price: parseFloat(t.execution_price),
          totalValue: parseFloat(t.quantity) * parseFloat(t.execution_price),
          slippage: parseFloat(t.execution_price) - parseFloat(t.requested_price)
        }));
        setTrades(formatted);
      });
  }, [teamId, apiKey]);
  
  return (
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Symbol</th>
          <th>Side</th>
          <th>Quantity</th>
          <th>Price</th>
          <th>Total Value</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((trade, i) => (
          <tr key={i}>
            <td>{trade.timestamp.toLocaleTimeString()}</td>
            <td>{trade.symbol}</td>
            <td>{trade.side}</td>
            <td>{trade.quantity.toFixed(2)}</td>
            <td>${trade.price.toFixed(2)}</td>
            <td>${trade.totalValue.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Python Example:

```python
import requests
from decimal import Decimal

def get_trades(team_id, api_key, limit=100):
    url = f"https://api.qtcq.xyz/api/v1/team/{team_id}/trades"
    params = {"key": api_key, "limit": limit}
    
    response = requests.get(url, params=params)
    data = response.json()
    
    # Transform trades
    trades = []
    for trade in data['trades']:
        trades.append({
            'timestamp': trade['timestamp'],
            'symbol': trade['symbol'],
            'side': trade['side'],
            'quantity': Decimal(trade['quantity']),
            'price': Decimal(trade['execution_price']),
            'total_value': Decimal(trade['quantity']) * Decimal(trade['execution_price']),
            'slippage': Decimal(trade['execution_price']) - Decimal(trade['requested_price']),
            'broker_order_id': trade.get('broker_order_id')
        })
    
    return trades
```

---

## Common Frontend Issues

### Issue 1: "Price is undefined"
**Cause:** Looking for `trade.price` field  
**Fix:** Use `trade.execution_price` instead

### Issue 2: "Math operations return NaN"
**Cause:** Not parsing string values  
**Fix:** Use `parseFloat()` on all numeric fields

### Issue 3: "Total value not showing"
**Cause:** Field doesn't exist in API  
**Fix:** Calculate it: `quantity × execution_price`

### Issue 4: "Position after trade not available"
**Cause:** Not included in trades response  
**Fix:** Track cumulatively or use snapshot endpoint

---

## Testing Your Integration

```bash
# Test command
curl "https://api.qtcq.xyz/api/v1/team/admin/trades?key=va5tKBRA5Q7CFdFyeyenMO1oZmO-HN8UdhaYuvDPKBQ&limit=5"

# Expected output structure
{
  "team_id": "admin",
  "count": 5,
  "trades": [
    {
      "team_id": "admin",
      "timestamp": "...",
      "symbol": "NVDA",
      "side": "buy",
      "quantity": "1.0",
      "requested_price": "182.23",
      "execution_price": "182.23",
      "order_type": "market",
      "broker_order_id": "..."
    }
  ]
}
```

---

## Summary Checklist

When integrating the trades endpoint:

- [ ] Parse `execution_price` as your price field
- [ ] Parse all numeric strings with `parseFloat()` or `Decimal()`
- [ ] Calculate `total_value` yourself (quantity × price)
- [ ] Handle positions separately (track cumulatively or use snapshot API)
- [ ] Handle both timestamp formats (space and T separator)
- [ ] Check for `broker_order_id` being null
- [ ] Most recent trades come first in the array

---

**The documentation is now accurate!** ✅

