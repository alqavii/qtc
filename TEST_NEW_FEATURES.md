# Testing New Alpaca Features - Quick Start Guide

This guide helps you test the new order type features (market vs limit orders, execution prices).

---

## What Was Updated

✅ **Admin Strategy** (`external_strategies/admin/strategy.py`)
- Now demonstrates **both market and limit orders**
- Shows **all time-in-force options**
- Includes 3 additional strategy variants:
  - `AggressiveStrategy` - Market orders only
  - `ConservativeStrategy` - Limit orders with GTC
  - `ScalpingStrategy` - IOC orders

✅ **Core Platform**
- Retrieves real execution prices from Alpaca
- Supports limit orders
- Records order types in trades

---

## Quick Test (Already Passed ✅)

The basic functionality test was just run successfully:

```bash
cd /opt/qtc
python3 -c "from external_strategies.admin.strategy import Strategy; ..."
```

**Results:**
- ✓ All 4 strategy classes imported successfully
- ✓ Signal generation works correctly
- ✓ Market orders configured properly
- ✓ Limit orders configured properly
- ✓ Order type and time_in_force fields present

---

## Testing with Live System

### 1. Test with Mock Data (Safe)

Run the orchestrator with admin strategy:

```bash
cd /opt/qtc
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:Strategy;10000" \
  --duration 5
```

**What to check:**
- Strategy loads without errors
- Signals generated with `order_type` field
- Trades recorded in `data/team/admin/trades.jsonl`
- Check execution_price vs requested_price

### 2. Verify Trade Records

After running, check the trades file:

```bash
cd /opt/qtc
tail -5 data/team/admin/trades.jsonl | jq
```

**Expected fields in each trade:**
```json
{
  "team_id": "admin",
  "symbol": "AAPL",
  "side": "buy",
  "quantity": "10",
  "requested_price": "150.50",
  "execution_price": "150.50",
  "order_type": "market",
  "broker_order_id": null,
  "timestamp": "2025-10-15T14:30:00+00:00"
}
```

### 3. Test via API

Start the API server:
```bash
cd /opt/qtc
uvicorn app.api.server:app --host 0.0.0.0 --port 8000
```

Get admin trades:
```bash
# Get your API key first
cat data/api_keys.json | jq -r '.admin'

# Use the key to fetch trades
curl "http://localhost:8000/api/v1/team/admin/trades?key=YOUR_KEY&limit=10" | jq
```

**Check for:**
- `execution_price` field present
- `order_type` field present
- `broker_order_id` field present

---

## Testing Different Order Types

### Test 1: Market Orders (Default)

The default `Strategy` class uses market orders for entries:

```python
# In strategy.py - line ~123
return {
    "symbol": symbol,
    "action": "buy",
    "quantity": quantity,
    "price": current_price,
    "order_type": "market"
}
```

**Expected behavior:**
- Order executes immediately
- `execution_price` may differ slightly from `requested_price`
- `broker_order_id` will be present (if Alpaca configured)

### Test 2: Limit Orders

Modify strategy to use limit orders:

```python
# In external_strategies/admin/strategy.py
# Change line 22 to True:
self.use_limit_orders = self.params.get('use_limit_orders', True)
```

Or pass as parameter:
```bash
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:Strategy;10000" \
  --team-params "admin:use_limit_orders=True"
```

**Expected behavior:**
- Order placed at limit price
- May not execute immediately
- Check Alpaca dashboard for open orders

### Test 3: Alternative Strategy Classes

Test the other strategy variants:

```bash
# Aggressive (market orders only)
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:AggressiveStrategy;10000"

# Conservative (limit orders with GTC)
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:ConservativeStrategy;10000"

# Scalping (IOC orders)
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:ScalpingStrategy;10000"
```

---

## Testing with Alpaca (Paper Trading)

### Setup

1. Ensure Alpaca credentials are configured:
```bash
cat /opt/qtc/etc/qtc-alpha/alpaca.env
```

Should contain:
```bash
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
ALPACA_PAPER=true
```

2. Start the orchestrator:
```bash
python3 -m app.main \
  --teams "admin;./external_strategies/admin;strategy:Strategy;10000" \
  --duration 10
```

### What to Monitor

**In Logs:**
```
[INFO] Alpaca market order submitted: abc123 for AAPL buy 10 @ 150.50
[INFO] Alpaca execution price: 150.52 (requested: 150.50)
```

**In Alpaca Dashboard:**
- Go to https://app.alpaca.markets/paper/dashboard
- Check "Orders" tab
- Verify orders are being placed
- Note the order IDs match `broker_order_id` in trades

**In Trade Records:**
```bash
tail -f data/team/admin/trades.jsonl
```

Look for:
- `broker_order_id` populated with Alpaca ID
- `execution_price` different from `requested_price`
- `order_type` showing "market" or "limit"

---

## Validation Checklist

### Basic Functionality ✅
- [x] Strategy imports successfully
- [x] Signals generated with order_type field
- [x] No linter errors

### Order Types
- [ ] Market orders execute immediately
- [ ] Limit orders placed at correct price
- [ ] Time-in-force options work (day, gtc, ioc, fok)

### Execution Prices
- [ ] `requested_price` recorded correctly
- [ ] `execution_price` retrieved from Alpaca
- [ ] Slippage visible in market orders
- [ ] Local-only mode uses requested_price

### API Endpoints
- [ ] `/trades` endpoint shows execution_price
- [ ] `/trades` endpoint shows order_type
- [ ] `/trades` endpoint shows broker_order_id
- [ ] Trade count matches actual trades

### Integration
- [ ] Alpaca orders visible in dashboard
- [ ] Order IDs match between platform and Alpaca
- [ ] Errors logged appropriately
- [ ] Rate limits not exceeded

---

## Common Issues & Solutions

### Issue: "No signal generated"
**Solution:** Strategy needs enough historical data (30+ bars). Wait 30 minutes or use backfill.

### Issue: "execution_price same as requested_price"
**Solution:** 
- Normal for local-only mode (no Alpaca)
- For Alpaca: Market may be closed, or 0.5s delay insufficient

### Issue: "broker_order_id is null"
**Solution:** 
- Check Alpaca credentials are configured
- Verify `ALPACA_PAPER=true` in alpaca.env
- Check logs for "Alpaca order submission failed"

### Issue: "Limit order not filling"
**Solution:**
- Normal behavior - limit orders wait for price
- Check Alpaca dashboard for open orders
- Price may never reach limit
- Consider using market orders or wider limits

### Issue: "Module import error"
**Solution:**
```bash
cd /opt/qtc
export PYTHONPATH=/opt/qtc:$PYTHONPATH
python3 -m app.main ...
```

---

## Advanced Testing

### Test Slippage Tracking

Compare requested vs execution prices:

```bash
cd /opt/qtc
python3 << 'EOF'
import json
from pathlib import Path

trades_file = Path("data/team/admin/trades.jsonl")
if trades_file.exists():
    slippages = []
    with open(trades_file, 'r') as f:
        for line in f:
            trade = json.loads(line)
            if trade.get('order_type') == 'market':
                req = float(trade.get('requested_price', 0))
                exe = float(trade.get('execution_price', 0))
                if req > 0:
                    slippage = ((exe - req) / req) * 100
                    slippages.append(slippage)
                    print(f"{trade['symbol']}: {slippage:.4f}% slippage")
    
    if slippages:
        avg_slippage = sum(slippages) / len(slippages)
        print(f"\nAverage slippage: {avg_slippage:.4f}%")
EOF
```

### Test Order Validation

Try invalid signals:

```python
# In strategy.py, temporarily return invalid signal
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.0,
    "order_type": "stop"  # Not yet supported - should be rejected
}
```

**Expected:** Error logged to `data/team/admin/errors.jsonl`

---

## Performance Benchmarks

Expected performance:
- Signal generation: < 100ms
- Order submission: < 200ms (with Alpaca)
- Execution price retrieval: < 600ms (0.5s delay + request)
- Total cycle time: < 1 second

Monitor with:
```bash
tail -f logs/qtc-orchestrator.log | grep "Alpaca"
```

---

## Next Steps

1. ✅ Basic tests passed
2. ⏳ Run with mock data for 5 minutes
3. ⏳ Verify trades in API endpoint
4. ⏳ Test with Alpaca paper trading
5. ⏳ Monitor for 1 hour
6. ⏳ Analyze slippage and fill rates
7. ⏳ Deploy to production teams

---

## Support

If issues arise:

1. **Check Logs:**
   ```bash
   tail -100 logs/qtc-orchestrator.log
   ```

2. **Check Errors:**
   ```bash
   cat data/team/admin/errors.jsonl | jq
   ```

3. **Verify Alpaca Status:**
   ```bash
   curl -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
        -H "APCA-API-SECRET-KEY: $ALPACA_API_SECRET" \
        https://paper-api.alpaca.markets/v2/account
   ```

4. **Review Documentation:**
   - [ALPACA_INTEGRATION.md](ALPACA_INTEGRATION.md)
   - [STRATEGY_SIGNAL_FORMAT.md](STRATEGY_SIGNAL_FORMAT.md)
   - [ALPACA_ENHANCEMENTS_SUMMARY.md](ALPACA_ENHANCEMENTS_SUMMARY.md)

---

**Test Status:** ✅ Initial tests passed  
**Ready for:** Extended testing with live system  
**Last Updated:** October 15, 2025

