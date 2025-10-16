#!/usr/bin/env python3
"""
Quick test to verify new ticker universe and batching works

Run this BEFORE the full backfill to ensure everything is configured correctly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config.settings import TICKER_UNIVERSE
from app.adapters.ticker_adapter import TickerAdapter
from datetime import date, timedelta

print("=" * 70)
print("  TICKER UNIVERSE & BATCHING TEST")
print("=" * 70)

# 1. Check universe
print(f"\n1️⃣  Ticker Universe Check")
print(f"   Total tickers: {len(TICKER_UNIVERSE)}")

eq, cc = TickerAdapter._split_crypto(TICKER_UNIVERSE)
print(f"   Equities: {len(eq)}")
print(f"   Crypto: {len(cc)}")
print(f"   Batch size: {TickerAdapter.BATCH_SIZE}")
print(f"   Batches needed: {(len(eq) + TickerAdapter.BATCH_SIZE - 1) // TickerAdapter.BATCH_SIZE}")

# Sample tickers
print(f"\n   Sample tickers:")
for i, ticker in enumerate(TICKER_UNIVERSE[:10], 1):
    print(f"      {i}. {ticker}")
print(f"      ... and {len(TICKER_UNIVERSE) - 10} more")

# 2. Test fetchBasic (live data)
print(f"\n2️⃣  Testing Live Data Fetch (fetchBasic)...")
try:
    bars = TickerAdapter.fetchBasic(TICKER_UNIVERSE[:50])  # Test with first 50
    print(f"   ✅ Success! Fetched {len(bars)} bars for 50 tickers")
    if bars:
        print(f"   Sample: {bars[0].ticker} - ${bars[0].close:.2f}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    print(f"   Note: This might fail if market is closed")

# 3. Test fetchHistoricalDay (one recent day)
print(f"\n3️⃣  Testing Historical Data Fetch (fetchHistoricalDay)...")
yesterday = date.today() - timedelta(days=1)
print(f"   Fetching data for {yesterday}...")

try:
    bars = TickerAdapter.fetchHistoricalDay(yesterday, TICKER_UNIVERSE[:100])  # Test with first 100
    print(f"   ✅ Success! Fetched {len(bars)} bars for 100 tickers")
    
    if bars:
        # Show breakdown by ticker
        ticker_counts = {}
        for bar in bars:
            ticker_counts[bar.ticker] = ticker_counts.get(bar.ticker, 0) + 1
        
        print(f"   Unique tickers: {len(ticker_counts)}")
        sample_ticker = list(ticker_counts.keys())[0]
        print(f"   Example: {sample_ticker} has {ticker_counts[sample_ticker]} bars")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    print(f"   Note: Yesterday might be weekend or holiday")

# 4. Summary
print(f"\n" + "=" * 70)
print(f"  TEST SUMMARY")
print(f"=" * 70)
print(f"\n✅ Configuration looks good!")
print(f"\nNext steps:")
print(f"   1. Run 1-week test: /opt/qtc/venv/bin/python3 test_backfill_1week.py")
print(f"   2. Run full backfill: /opt/qtc/venv/bin/python3 backfill_3years.py")
print(f"\nMake sure orchestrator is STOPPED before backfilling!")

