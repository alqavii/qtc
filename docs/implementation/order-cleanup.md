# Pending Orders Cleanup Implementation

**Date:** October 16, 2025  
**Status:** ✅ Implemented

---

## Overview

The order tracking system now properly cleans up filled/cancelled orders from `pending_orders.jsonl` files, preventing indefinite file growth.

---

## How It Works

### **Before (Old Behavior):**

```
pending_orders.jsonl (append-only):
Line 1: {"order_id": "abc-123", "status": "new", ...}      ← Initial order
Line 2: {"order_id": "abc-123", "status": "filled", ...}   ← Appended when filled
Line 3: {"order_id": "def-456", "status": "new", ...}      ← Another order
Line 4: {"order_id": "def-456", "status": "filled", ...}   ← Filled
...
Line 52: Still contains all filled orders! ❌
```

**Problem:** File grows indefinitely, filled orders never removed.

---

### **After (New Behavior):**

```
pending_orders.jsonl (rewritten when orders fill):
Line 1: {"order_id": "xyz-789", "status": "new", ...}      ← Only current open orders
Line 2: {"order_id": "mno-012", "status": "new", ...}      ← Active pending order
```

**Fixed:** File only contains truly pending orders, stays small.

---

## Implementation Details

### **What Changed:**

**File:** `app/services/order_tracker.py`

**Added Method:** `_rewrite_pending_files()`
- Collects all currently pending orders from memory
- Rewrites `pending_orders.jsonl` for each team
- Only includes orders with status: `new`, `partially_filled`, `accepted`
- Deletes file if no pending orders remain

**Updated Method:** `update_order_status()`
- When order fills → creates trade record → removes from memory → **rewrites file**
- When order cancelled/rejected/expired → removes from memory → **rewrites file**

**Updated Method:** `cleanup_old_orders()`
- Removes old filled/cancelled orders (older than 7 days)
- Calls `_rewrite_pending_files()` to clean up disk

---

## Lifecycle of an Order

```
1. Order Placed
   ├─ Sent to Alpaca
   ├─ Added to memory: order_tracker.pending_orders[order_id]
   └─ Appended to: pending_orders.jsonl

2. Reconciliation (every 5 minutes)
   ├─ Query Alpaca for status
   ├─ Update order in memory
   └─ If status changed → call update_order_status()

3. Order Fills
   ├─ Create trade record → trades.jsonl (permanent)
   ├─ Remove from memory
   └─ Rewrite pending_orders.jsonl (without this order) ✅ NEW

4. Daily Cleanup (every 5 minutes)
   ├─ Remove filled orders older than 7 days from memory
   └─ Rewrite files to match memory ✅ NEW
```

---

## Data Storage

### **Filled Orders:**
- ✅ **Preserved** in `trades.jsonl` (permanent record)
- ✅ **Removed** from `pending_orders.jsonl` (cleanup)

### **Pending Orders:**
- ✅ **In memory** for fast access (order_tracker.pending_orders)
- ✅ **On disk** for persistence (pending_orders.jsonl)
- ✅ **Rewritten** when status changes (keeps file clean)

---

## Reconciliation Schedule

**Orchestrator runs background job** (line 582-603 in main.py):

```python
async def _reconcile_orders_loop():
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        
        # Check Alpaca for order status
        await order_tracker.reconcile_with_broker(broker)
        
        # Clean up old filled orders
        order_tracker.cleanup_old_orders(max_age_days=7)
```

**Actions every 5 minutes:**
1. Query Alpaca for all pending orders
2. Update statuses (new → partially_filled → filled)
3. Create trade records for filled orders
4. Remove filled orders from pending
5. Rewrite `pending_orders.jsonl` files
6. Clean up orders older than 7 days

---

## File Examples

### **pending_orders.jsonl** (Current Open Orders Only)

```json
{"order_id": "abc-123", "symbol": "NVDA", "status": "new", "limit_price": "530.00", ...}
{"order_id": "def-456", "symbol": "SPY", "status": "partially_filled", "filled_qty": "5", ...}
```

### **trades.jsonl** (Permanent Trade History)

```json
{"team_id": "admin", "symbol": "NVDA", "side": "buy", "execution_price": "525.30", ...}
{"team_id": "admin", "symbol": "AAPL", "side": "sell", "execution_price": "225.50", ...}
```

---

## Benefits

✅ **File Size Control** - pending_orders.jsonl stays small  
✅ **Accurate API Responses** - `/orders/open` only shows truly open orders  
✅ **Complete History** - Filled orders preserved in trades.jsonl  
✅ **Memory Efficiency** - Old orders cleaned up after 7 days  
✅ **Crash Recovery** - Pending orders reloaded from file on startup  

---

## Testing

After restarting orchestrator, verify the cleanup works:

```bash
# Check pending orders
curl "https://api.qtcq.xyz/api/v1/team/admin/orders/open?key=YOUR_KEY" | jq

# Should only show orders with status: "new" or "partially_filled"
# Filled orders should NOT appear

# Check the file directly
cat /opt/qtc/data/team/admin/pending_orders.jsonl | wc -l
# Should match the number of open orders (or not exist if none pending)

# Check trades.jsonl has the filled orders
tail -10 /opt/qtc/data/team/admin/trades.jsonl
```

---

## Next Restart Required

The orchestrator needs to be restarted to:
- Load the new cleanup logic
- Start the reconciliation loop
- Begin cleaning up old filled orders

```bash
# After backfill completes
sudo systemctl restart qtc-orchestrator
```

---

**Status:** ✅ Implemented and ready to use once orchestrator restarts!

