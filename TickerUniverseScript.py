#!/usr/bin/env python3
"""
Fetch all available assets from Alpaca and save to CSV
"""
import os
import csv
from pathlib import Path

# Manually load from the alpaca.env file
env_file = Path("/etc/qtc-alpha/alpaca.env")

env_vars = {}
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
                os.environ[key] = value

# Import after setting env vars
from alpaca.trading.client import TradingClient

print("🔄 Connecting to Alpaca API...")
client = TradingClient(
    api_key=env_vars.get("ALPACA_API_KEY"),
    secret_key=env_vars.get("ALPACA_API_SECRET"),
    paper=True
)

print("📥 Fetching all assets...")
all_assets = client.get_all_assets()

print(f"✅ Total assets fetched: {len(all_assets)}")

# Count by status
active_tradable = [a for a in all_assets if a.status == 'active' and a.tradable]
print(f"✅ Active & tradable: {len(active_tradable)}")

# Save to CSV
output_file = Path(__file__).parent / "alpaca_assets.csv"

print(f"\n💾 Saving all assets to: {output_file}")

with open(output_file, 'w', newline='') as csvfile:
    fieldnames = [
        'symbol', 
        'name', 
        'asset_class',
        'status', 
        'tradable', 
        'marginable',
        'shortable',
        'easy_to_borrow',
        'fractionable',
        'exchange'
    ]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    
    writer.writeheader()
    
    for asset in all_assets:
        writer.writerow({
            'symbol': asset.symbol,
            'name': getattr(asset, 'name', ''),
            'asset_class': getattr(asset, 'asset_class', ''),
            'status': asset.status,
            'tradable': asset.tradable,
            'marginable': getattr(asset, 'marginable', False),
            'shortable': getattr(asset, 'shortable', False),
            'easy_to_borrow': getattr(asset, 'easy_to_borrow', False),
            'fractionable': getattr(asset, 'fractionable', False),
            'exchange': getattr(asset, 'exchange', '')
        })

print(f"📊 Total rows: {len(all_assets)}")

# Also create a filtered file with only active & tradable
active_file = Path(__file__).parent / "alpaca_assets_tradable.csv"

print(f"\n💾 Saving tradable-only assets to: {active_file}")

with open(active_file, 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    
    for asset in active_tradable:
        writer.writerow({
            'symbol': asset.symbol,
            'name': getattr(asset, 'name', ''),
            'asset_class': getattr(asset, 'asset_class', ''),
            'status': asset.status,
            'tradable': asset.tradable,
            'marginable': getattr(asset, 'marginable', False),
            'shortable': getattr(asset, 'shortable', False),
            'easy_to_borrow': getattr(asset, 'easy_to_borrow', False),
            'fractionable': getattr(asset, 'fractionable', False),
            'exchange': getattr(asset, 'exchange', '')
        })

print(f"📊 Total tradable rows: {len(active_tradable)}")

# Show sample of popular tickers
print("\n🔍 Sample of popular tickers:")
test_symbols = ["AAPL", "NVDA", "TSLA", "SPY", "QQQ", "BTC/USD", "ETH/USD"]
for symbol in test_symbols:
    try:
        asset = client.get_asset(symbol)
        status = "✅" if asset.tradable else "❌"
        frac = "F" if getattr(asset, 'fractionable', False) else " "
        print(f"{status} {asset.symbol:10} [{frac}] - {asset.name[:35]:35} (status: {asset.status})")
    except Exception as e:
        print(f"❌ {symbol:10} - Not found")

print("\n✅ Done! Files created:")
print(f"   📄 alpaca_assets.csv (all {len(all_assets)} assets)")
print(f"   📄 alpaca_assets_tradable.csv (only {len(active_tradable)} tradable assets)")
