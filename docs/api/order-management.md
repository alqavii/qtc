# Order Management API - New Endpoints

**Version:** 2.0  
**Last Updated:** October 15, 2025

---

## Overview

New endpoints for managing and monitoring open orders, especially limit orders that may not fill immediately.

### Key Features
- ✅ **Real-time order status** - Updated every 30 seconds
- ✅ **Monitor pending limit orders** - See what's waiting to fill
- ✅ **Cancel orders** - Close GTC or unwanted limit orders
- ✅ **Track partial fills** - Know how much has executed
- ✅ **Automatic execution price updates** - Background reconciliation

---

## Endpoints

### 1. Get Open Orders
**GET** `/api/v1/team/{team_id}/orders/open`

Get all open (pending) orders for a team.

**Authentication:** Required (API key)

**Example:**
```bash
curl "http://localhost:8000/api/v1/team/epsilon/orders/open?key=YOUR_API_KEY"
```

**Response:**
```json
{
  "team_id": "epsilon",
  "open_orders_count": 2,
  "orders": [
    {
      "order_id": "abc-123-alpaca",
      "symbol": "NVDA",
      "side": "sell",
      "quantity": 10,
      "order_type": "limit",
      "limit_price": 530.00,
      "status": "new",
      "filled_qty": 0,
      "filled_avg_price": null,
      "time_in_force": "day",
      "created_at": "2025-10-15T14:30:00Z",
      "updated_at": "2025-10-15T14:30:00Z",
      "requested_price": 530.00,
      "broker_order_id": "abc-123-alpaca"
    }
  ]
}
```

**Status Values:**
- `new` - Waiting to fill
- `partially_filled` - Partially executed
- `accepted` - Acknowledged by broker

---

### 2. Get Order Details
**GET** `/api/v1/team/{team_id}/orders/{order_id}`

Get detailed status of specific order.

**Example:**
```bash
curl "http://localhost:8000/api/v1/team/epsilon/orders/abc-123?key=YOUR_API_KEY"
```

**Response:**
```json
{
  "order_id": "abc-123-alpaca",
  "team_id": "epsilon",
  "symbol": "NVDA",
  "status": "partially_filled",
  "filled_qty": 5,
  "filled_avg_price": 530.25,
  "quantity": 10,
  "limit_price": 530.00
}
```

---

### 3. Cancel Order
**DELETE** `/api/v1/team/{team_id}/orders/{order_id}`

Cancel an open order.

**Example:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/team/epsilon/orders/abc-123?key=YOUR_API_KEY"
```

**Success Response:**
```json
{
  "success": true,
  "order_id": "abc-123-alpaca",
  "message": "Order cancelled successfully",
  "status": "cancelled"
}
```

**Error Response:**
```json
{
  "detail": "Order not found or already closed"
}
```

---

## How It Works

### Background Reconciliation

The platform runs a background job every 30 seconds that:

1. **Checks all pending orders** with Alpaca
2. **Updates statuses** (new → partially_filled → filled)
3. **Records execution prices** when orders fill
4. **Creates trade records** for filled orders
5. **Cleans up old orders** (hourly)

### Order Lifecycle

```
Strategy generates signal
         ↓
   Place order with Alpaca
         ↓
   Store as PendingOrder
         ↓
┌─────────────────────────┐
│ Background Job (30s)    │
│ 1. Query Alpaca         │
│ 2. Update status        │
│ 3. Get execution price  │
│ 4. If filled → Trade    │
└─────────────────────────┘
```

### Limit Order Example

**Minute 1:**
- Strategy: SELL 10 NVDA @ $530 (limit)
- Platform: Places limit order
- Status: `"new"`, `filled_avg_price: null`

**Minute 2-5:**
- Background job checks every 30s
- Price at $528 - not filled yet
- Status: Still `"new"`

**Minute 6:**
- Price reaches $530.25
- Alpaca fills order at $530.25
- Background job detects fill
- Updates: `status: "filled"`, `filled_avg_price: 530.25`
- Creates trade record with `execution_price: 530.25`
- Removes from pending orders
- Updates portfolio with actual execution price

---

## Use Cases

### Monitor Strategy Behavior
```javascript
// Check why position didn't change
const response = await fetch(
  `http://api/v1/team/epsilon/orders/open?key=${apiKey}`
);
const { orders } = await response.json();

if (orders.length > 0) {
  console.log('Strategy placed orders but they haven\'t filled yet:');
  orders.forEach(o => {
    console.log(`  ${o.symbol}: ${o.status} - ${o.filled_qty}/${o.quantity} filled`);
  });
}
```

### Dashboard Display
```javascript
// Show pending orders with current market price
orders.forEach(order => {
  const currentPrice = prices[order.symbol];
  const distance = ((currentPrice - order.limit_price) / order.limit_price * 100).toFixed(2);
  
  console.log(`${order.symbol}: Limit @ $${order.limit_price}`);
  console.log(`  Current: $${currentPrice} (${distance}% away)`);
  console.log(`  Status: ${order.filled_qty}/${order.quantity} filled`);
});
```

### Cancel Unwanted Orders
```bash
# Strategy changed mind, cancel GTC order
curl -X DELETE \
  "http://localhost:8000/api/v1/team/epsilon/orders/abc-123?key=$API_KEY"
```

---

## Frontend Integration

### React Example
```javascript
function OrderMonitor({ teamId, apiKey }) {
  const [openOrders, setOpenOrders] = useState([]);
  
  useEffect(() => {
    const fetchOrders = async () => {
      const res = await fetch(
        `/api/v1/team/${teamId}/orders/open?key=${apiKey}`
      );
      const data = await res.json();
      setOpenOrders(data.orders);
    };
    
    // Poll every 30 seconds
    fetchOrders();
    const interval = setInterval(fetchOrders, 30000);
    return () => clearInterval(interval);
  }, [teamId, apiKey]);
  
  return (
    <div>
      <h3>Pending Orders ({openOrders.length})</h3>
      {openOrders.map(order => (
        <OrderCard
          key={order.order_id}
          order={order}
          onCancel={() => cancelOrder(order.order_id)}
        />
      ))}
    </div>
  );
}
```

---

## Rate Limits

| Endpoint | Limit | Notes |
|----------|-------|-------|
| `GET /orders/open` | 60/minute | Safe to poll every 30-60s |
| `GET /orders/{id}` | 60/minute | On-demand queries |
| `DELETE /orders/{id}` | 30/minute | Manual cancellations |

---

## Testing

### Test 1: Place Limit Order
```bash
# 1. Place a limit order via admin strategy
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:Strategy;100000" \
  --duration 2

# 2. Check for open orders
curl "http://localhost:8000/api/v1/team/admin/orders/open?key=YOUR_KEY" | jq
```

### Test 2: Monitor Fill Progress
```bash
# Watch order status update
watch -n 5 'curl -s "http://localhost:8000/api/v1/team/admin/orders/open?key=YOUR_KEY" | jq ".orders[0].status"'
```

### Test 3: Cancel Order
```bash
# Get order ID
ORDER_ID=$(curl -s "http://localhost:8000/api/v1/team/admin/orders/open?key=YOUR_KEY" | jq -r '.orders[0].order_id')

# Cancel it
curl -X DELETE "http://localhost:8000/api/v1/team/admin/orders/$ORDER_ID?key=YOUR_KEY" | jq
```

---

## Comparison: Trades vs Orders

| Feature | `/trades` Endpoint | `/orders/open` Endpoint |
|---------|-------------------|------------------------|
| **Shows** | Completed trades | Pending orders |
| **Status** | Always filled | new, partially_filled |
| **Execution Price** | Always populated | null until filled |
| **Use When** | Analyzing history | Monitoring current |
| **Updates** | Never (historical) | Every 30s (live) |
| **Actions** | Read-only | Can cancel |

**Workflow:**
1. Strategy places order → Appears in `/orders/open`
2. Order fills → Moves to `/trades`, removed from `/orders/open`
3. Order cancelled → Removed from `/orders/open`, never in `/trades`

---

## Architecture

### Data Storage

```
data/team/{team_id}/
  ├── trades.jsonl          # Completed trades (filled orders)
  ├── pending_orders.jsonl  # Open orders (limit orders, etc.)
  └── portfolio/            # Portfolio snapshots
```

### Background Reconciliation Job

**Runs:** Every 30 seconds  
**Checks:** All pending orders against Alpaca API  
**Updates:** Status, filled_qty, filled_avg_price  
**Cleanup:** Hourly removal of old filled/cancelled orders (7+ days)

**Benefits:**
- Execution prices updated automatically
- No polling overhead on users
- Works even if API not queried
- Handles overnight GTC orders

---

## Error Handling

### Order Not Found (404)
- Order already filled (moved to trades)
- Order cancelled
- Invalid order ID
- Order from different team

### Broker Unavailable (503)
- Local-only mode (no Alpaca)
- Alpaca credentials missing
- Alpaca API down

### Cancellation Failed (500)
- Order already filled
- Order doesn't exist on Alpaca
- Network error

---

## Best Practices

1. **Poll `/orders/open` every 30-60 seconds** - Matches background update frequency
2. **Check before placing duplicate orders** - Avoid stacking limit orders
3. **Cancel GTC orders** - Don't let them accumulate
4. **Monitor partial fills** - Understand actual position size
5. **Use order status in UI** - Show users what's pending
6. **Handle empty responses** - No open orders is normal for market-only strategies

---

## See Also

- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Complete API reference
- [ALPACA_INTEGRATION.md](ALPACA_INTEGRATION.md) - Alpaca integration details  
- [STRATEGY_SIGNAL_FORMAT.md](STRATEGY_SIGNAL_FORMAT.md) - Strategy signal format
- [ALPACA_ENHANCEMENTS_SUMMARY.md](ALPACA_ENHANCEMENTS_SUMMARY.md) - Implementation summary

---

**Status:** ✅ Fully implemented and tested  
**Ready for:** Production use

