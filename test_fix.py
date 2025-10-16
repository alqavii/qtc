#!/usr/bin/env python3
"""
Quick test to verify the fix works
"""
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, '/opt/qtc')

from app.adapters.ticker_adapter import TickerAdapter

print("Testing fixed fetchHistoricalDay...")
print("=" * 70)

# Test with Oct 2022 (the date that was failing)
test_date = date(2022, 10, 20)
print(f"\nFetching {test_date} for 5 test symbols...")

test_symbols = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
bars = TickerAdapter.fetchHistoricalDay(test_date, test_symbols)

print(f"\n✅ Result: {len(bars)} bars fetched")

if bars:
    # Show breakdown by ticker
    ticker_counts = {}
    for bar in bars:
        ticker_counts[bar.ticker] = ticker_counts.get(bar.ticker, 0) + 1
    
    print(f"\nBreakdown:")
    for ticker, count in sorted(ticker_counts.items()):
        print(f"   {ticker}: {count} bars")
    
    # Show sample bar
    print(f"\nSample bar:")
    print(f"   {bars[0].ticker} @ {bars[0].timestamp}")
    print(f"   O:{bars[0].open} H:{bars[0].high} L:{bars[0].low} C:{bars[0].close}")
    print(f"\n🎉 FIX WORKS! Old data is now accessible!")
else:
    print("❌ Still no data - something else is wrong")

print("\n" + "=" * 70)
print("✅ If you see bars above, the fix worked!")
print("You can now run: sudo /opt/qtc/venv/bin/python3 backfill_3years.py")

