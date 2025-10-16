#!/usr/bin/env python3
"""
Simple test of Alpaca API response
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os

sys.path.insert(0, '/opt/qtc')
from app.adapters.alpaca_broker import _ensure_alpaca_env_loaded

_ensure_alpaca_env_loaded()

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

client = StockHistoricalDataClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_API_SECRET")
)

# Test with a recent date that SHOULD have data
test_date = datetime.now() - timedelta(days=7)
eastern = ZoneInfo("America/New_York")
start = datetime(test_date.year, test_date.month, test_date.day, 9, 30, tzinfo=eastern)
end = start + timedelta(hours=1)  # Just 1 hour

print(f"Testing AAPL from {start} to {end}")
print("=" * 70)

req = StockBarsRequest(
    symbol_or_symbols=["AAPL"],
    timeframe=TimeFrame.Minute,
    start=start,
    end=end,
    limit=100,
)

response = client.get_stock_bars(req)

print(f"\nResponse type: {type(response)}")
print(f"Response: {response}")

# Check different ways to access data
if hasattr(response, 'data'):
    print(f"\n✅ Has .data attribute")
    print(f"Data type: {type(response.data)}")
    print(f"Data length: {len(response.data) if hasattr(response.data, '__len__') else 'N/A'}")
    if response.data:
        print(f"First item: {response.data[0] if isinstance(response.data, list) else 'dict-like'}")

if hasattr(response, 'items'):
    print(f"\n✅ Has .items() method (dict-like)")
    try:
        for symbol, bars in response.items():
            print(f"Symbol: {symbol}, Bars type: {type(bars)}, Count: {len(bars) if hasattr(bars, '__len__') else 'N/A'}")
            if bars and hasattr(bars, '__iter__'):
                for i, bar in enumerate(bars):
                    if i < 3:
                        print(f"  Bar {i}: {bar.timestamp} Close: {bar.close}")
    except Exception as e:
        print(f"Error iterating: {e}")

if hasattr(response, '__iter__'):
    print(f"\n✅ Is iterable")
    try:
        items = list(response)
        print(f"Items count: {len(items)}")
        if items:
            print(f"First item: {items[0]}")
    except Exception as e:
        print(f"Error converting to list: {e}")

print("\n" + "=" * 70)
print("Now testing with OLD date (Oct 2022):")
print("=" * 70)

old_date = datetime(2022, 10, 20, 9, 30, tzinfo=eastern)
old_end = old_date + timedelta(hours=1)

print(f"Testing AAPL from {old_date} to {old_end}")

req2 = StockBarsRequest(
    symbol_or_symbols=["AAPL"],
    timeframe=TimeFrame.Minute,
    start=old_date,
    end=old_end,
    limit=100,
)

response2 = client.get_stock_bars(req2)
print(f"Response type: {type(response2)}")

if hasattr(response2, 'data'):
    bars_count = len(response2.data) if hasattr(response2.data, '__len__') else 0
    print(f"Data count: {bars_count}")
    if bars_count > 0:
        print("✅ OLD data IS available!")
    else:
        print("❌ OLD data returns empty")

if hasattr(response2, 'items'):
    try:
        items = dict(response2.items())
        if items:
            for sym, bars in items.items():
                print(f"✅ {sym}: {len(bars) if hasattr(bars, '__len__') else 0} bars")
        else:
            print("❌ items() returns empty dict")
    except Exception as e:
        print(f"Error: {e}")

