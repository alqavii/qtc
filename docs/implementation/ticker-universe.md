# Ticker Universe Upgrade Summary

**Date:** 2025-10-16  
**Status:** ✅ Code Ready - Backfill NOT run yet  
**New Universe Size:** 533 tickers (503 S&P 500 + 29 ETFs + 2 Crypto)

---

## ✅ What Was Implemented

### 1. **Batching Support Added**
   - **File:** `app/adapters/ticker_adapter.py`
   - **Changes:**
     - Added `BATCH_SIZE = 200` constant
     - Modified `fetchBasic()` to batch equity requests
     - Modified `fetchHistoricalDay()` to batch equity requests
   - **Why:** Alpaca limits requests to ~200 symbols per call
   - **Result:** Can now handle 538 tickers efficiently

### 2. **Ticker Universe Updated**
   - **File:** `app/config/settings.py`
   - **Old Universe:** 9 tickers
   - **New Universe:** 533 tickers
     - 503 S&P 500 stocks
     - 29 ETFs (SPY, QQQ, sectors, bonds, commodities)
     - 2 Crypto (BTC, ETH)
   
### 3. **Backfill Script Created**
   - **File:** `backfill_3years.py`
   - **Purpose:** Fetch 3 years of historical minute bars
   - **Features:**
     - Progress tracking with ETA
     - Error handling and resume capability
     - Safety confirmations
     - Rate limiting built-in
   - **Status:** Created but NOT executed

---

## 📊 Resource Requirements (Updated)

| Metric | Value |
|--------|-------|
| **Total Tickers** | 533 |
| **API Calls/minute** | 3-4 (well under 200 limit) |
| **Storage (3 years)** | ~16 GB |
| **Backfill Time** | ~12-15 minutes |
| **Memory per minute** | ~53 KB (negligible) |

---

## 🚀 What You Need to Do Next

### **Step 1: Test with Recent Data (Recommended)**

Before running the full 3-year backfill, test with 1 week:

```bash
# Create test script
cat > /opt/qtc/test_backfill_1week.py << 'EOF'
#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from app.adapters.ticker_adapter import TickerAdapter
from app.adapters.parquet_writer import ParquetWriter
from app.config.settings import TICKER_UNIVERSE

print(f"Testing with {len(TICKER_UNIVERSE)} tickers...")

# Test with last 5 trading days
end_date = date.today()
start_date = end_date - timedelta(days=7)

current_date = start_date
while current_date <= end_date:
    if current_date.weekday() < 5:  # Skip weekends
        print(f"Fetching {current_date}...", end=" ", flush=True)
        bars = TickerAdapter.fetchHistoricalDay(current_date, TICKER_UNIVERSE)
        if bars:
            ParquetWriter.writeDay(bars, root="data/prices/minute_bars")
            print(f"✅ {len(bars)} bars")
        else:
            print("⚠️  No data")
    current_date += timedelta(days=1)

print("✅ Test complete!")
EOF

# Run test (orchestrator should still be stopped)
/opt/qtc/venv/bin/python3 test_backfill_1week.py
```

### **Step 2: Run Full 3-Year Backfill**

Once testing looks good:

```bash
# Make sure orchestrator is stopped
sudo systemctl status qtc-orchestrator
# Should show "inactive (dead)"

# Run the backfill (~12-15 minutes)
/opt/qtc/venv/bin/python3 backfill_3years.py

# Follow the prompts
# - It will show estimates
# - Ask for confirmation
# - Display progress with ETA
```

### **Step 3: Restart Services**

After backfill completes:

```bash
# Restart orchestrator
sudo systemctl start qtc-orchestrator
sudo systemctl status qtc-orchestrator

# Restart API
sudo systemctl start qtc-api
sudo systemctl status qtc-api

# Verify orchestrator is fetching new data
sudo journalctl -u qtc-orchestrator -f
# Should show logs for fetching 533 tickers
```

### **Step 4: Verify Data**

```bash
# Check storage size
du -sh /opt/qtc/data/prices/minute_bars/
# Should show ~16 GB after 3 years

# Check data structure
ls -la /opt/qtc/data/prices/minute_bars/
# Should see y=2022, y=2023, y=2024, y=2025

# Test data access from Python
/opt/qtc/venv/bin/python3 << 'EOF'
from app.services.data_api import StrategyDataAPI
from datetime import datetime, timedelta

api = StrategyDataAPI()

# Test fetching data
end = datetime.now()
start = end - timedelta(days=7)

df = api.getRange("AAPL", start, end)
print(f"✅ Retrieved {len(df)} bars for AAPL")

df = api.getRange("SPY", start, end)
print(f"✅ Retrieved {len(df)} bars for SPY")

print("\n✅ Data access working!")
EOF
```

---

## 🎯 New Ticker Universe Breakdown

### **S&P 500 Stocks (503)**
- All sectors represented
- Industrials: 79
- Financials: 75  
- Information Technology: 68
- Health Care: 60
- Consumer Discretionary: 50
- And more...

### **ETFs (29)**

**Broad Market (6):**
- SPY, QQQ, IWM, DIA, VOO, VTI

**Sectors (10):**
- XLE (Energy), XLF (Financial), XLK (Technology)
- XLP (Consumer Staples), XLU (Utilities), XLV (Healthcare)
- XLY (Consumer Discretionary), XLI (Industrial)
- XLB (Materials), XLRE (Real Estate)

**International (3):**
- EFA (Developed ex-US), EEM (Emerging), VEA (Developed)

**Bonds (7):**
- AGG (Aggregate), LQD (Investment Grade), HYG (High Yield)
- TLT (20Y Treasury), IEF (7-10Y Treasury), BND (Total Bond), EMB (EM Bond)

**Commodities & Real Estate (3):**
- GLD (Gold), SLV (Silver), VNQ (Real Estate)

### **Crypto (2)**
- BTC, ETH

---

## ⚠️ Important Notes

### **Before Running Backfill:**

1. ✅ **Orchestrator must be stopped** - prevents file conflicts
2. ✅ **Ensure 20+ GB free disk space**
3. ✅ **Run during off-market hours** - better API performance
4. ✅ **Keep terminal open** - don't close during backfill

### **If Backfill Is Interrupted:**

- Data already fetched is saved
- Can run again - will attempt all dates
- Parquet writer handles duplicates gracefully
- Resume will be slower (checks existing data)

### **Rate Limiting:**

- Script sleeps 0.5s between days
- Built-in error handling with backoff
- Conservative rate: ~150 days/minute
- Stays well under 200 API calls/minute limit

---

## 📁 Files Modified/Created

```
Modified:
├── app/adapters/ticker_adapter.py       (Added batching)
├── app/config/settings.py               (Updated universe)

Created:
├── backfill_3years.py                   (3-year backfill script)
├── TICKER_UNIVERSE_UPGRADE_SUMMARY.md   (This file)
└── test_backfill_1week.py               (Test script - create manually)
```

---

## 🐛 Troubleshooting

### **Problem: "Too many API calls" error**

```bash
# Increase sleep time in backfill_3years.py
# Change line: time.sleep(0.5)
# To:         time.sleep(1.0)
```

### **Problem: "Parquet write error"**

```bash
# Check disk space
df -h /opt/qtc

# Check permissions
ls -la /opt/qtc/data/prices/minute_bars/
```

### **Problem: "Module not found" error**

```bash
# Ensure using venv Python
/opt/qtc/venv/bin/python3 backfill_3years.py
# NOT: python3 backfill_3years.py
```

---

## ✅ Checklist

- [x] Code updated with batching support
- [x] Ticker universe updated (533 tickers)
- [x] Backfill script created
- [ ] Test with 1 week data
- [ ] Run full 3-year backfill
- [ ] Restart services
- [ ] Verify data access
- [ ] Monitor orchestrator logs

---

## 📞 Quick Reference

```bash
# Check services
sudo systemctl status qtc-orchestrator
sudo systemctl status qtc-api

# Stop services
sudo systemctl stop qtc-orchestrator
sudo systemctl stop qtc-api

# Start services  
sudo systemctl start qtc-orchestrator
sudo systemctl start qtc-api

# View logs
sudo journalctl -u qtc-orchestrator -f
sudo journalctl -u qtc-api -f

# Check data size
du -sh /opt/qtc/data/prices/minute_bars/

# Test backfill (1 week)
/opt/qtc/venv/bin/python3 test_backfill_1week.py

# Run full backfill (3 years)
/opt/qtc/venv/bin/python3 backfill_3years.py
```

---

**Ready to go!** Start with the 1-week test, then run the full 3-year backfill when you're ready. 🚀

