#!/usr/bin/env python3
"""
Debug script to check Alpaca data availability
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, '/opt/qtc')

from app.adapters.alpaca_broker import _ensure_alpaca_env_loaded
import os

_ensure_alpaca_env_loaded()

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Initialize client
client = StockHistoricalDataClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_API_SECRET")
)

print("=" * 70)
print("  ALPACA DATA AVAILABILITY DEBUG")
print("=" * 70)

# Test various dates and symbols
test_cases = [
    ("Recent (7 days ago)", date.today() - timedelta(days=7)),
    ("30 days ago", date.today() - timedelta(days=30)),
    ("6 months ago", date.today() - timedelta(days=180)),
    ("1 year ago", date.today() - timedelta(days=365)),
    ("2 years ago", date.today() - timedelta(days=730)),
    ("3 years ago (Oct 2022)", date(2022, 10, 20)),
]

test_symbols = ["AAPL", "SPY"]

for description, test_date in test_cases:
    print(f"\n{'='*70}")
    print(f"Testing: {description} - {test_date}")
    print(f"{'='*70}")
    
    eastern = ZoneInfo("America/New_York")
    start = datetime(test_date.year, test_date.month, test_date.day, 0, 0, tzinfo=eastern)
    end = start + timedelta(days=1)
    
    for symbol in test_symbols:
        try:
            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
                limit=10,  # Just get a few bars to test
            )
            
            print(f"\n  Testing {symbol}:")
            print(f"    Request: {start} to {end}")
            
            barset = client.get_stock_bars(req)
            
            # Check if we got data
            if hasattr(barset, 'data'):
                bars = barset.data
            elif hasattr(barset, '__iter__'):
                bars = list(barset)
            else:
                bars = []
            
            if bars:
                print(f"    ✅ Got {len(bars)} bars")
                # Show first bar
                first_bar = bars[0]
                print(f"    First bar: {first_bar.timestamp} O:{first_bar.open} H:{first_bar.high} L:{first_bar.low} C:{first_bar.close}")
            else:
                print(f"    ❌ NO DATA returned")
                print(f"    Barset type: {type(barset)}")
                print(f"    Barset: {barset}")
                
        except Exception as e:
            print(f"    ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

print("\n" + "=" * 70)
print("  CONCLUSION")
print("=" * 70)
print("\nBased on the results above:")
print("- If recent dates work but old dates don't: Data availability issue")
print("- If all dates fail: Authentication or API issue")
print("- If some symbols work but others don't: Symbol-specific issue")

