#!/usr/bin/env python3
"""
Generate S&P 500 ticker universe from Alpaca tradable assets
"""
import pandas as pd
from pathlib import Path

print("📥 Fetching S&P 500 constituents from Wikipedia...")

# Fetch S&P 500 list from Wikipedia (always up to date)
# Add user agent to avoid 403 errors
import requests
from io import StringIO

url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
response = requests.get(url, headers=headers)
sp500_df = pd.read_html(StringIO(response.text))[0]
sp500_symbols = set(sp500_df['Symbol'].tolist())

print(f"✅ Found {len(sp500_symbols)} S&P 500 companies")

# Read your tradable Alpaca assets
print("\n📂 Reading alpaca_assets_tradable.csv...")
tradable_df = pd.read_csv('alpaca_assets_tradable.csv')

# Filter for S&P 500 companies that are tradable on Alpaca
sp500_tradable = tradable_df[tradable_df['symbol'].isin(sp500_symbols)]

print(f"✅ Found {len(sp500_tradable)} S&P 500 stocks tradable on Alpaca")

# Sort by symbol for cleaner output
sp500_tradable = sp500_tradable.sort_values('symbol')

# Generate Python list
symbols = sp500_tradable['symbol'].tolist()

print(f"\n💾 Generating ticker universe for settings.py...")

# Create output with nice formatting
output = f"""# S&P 500 Ticker Universe (Auto-generated)
# Total: {len(symbols)} stocks
# Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}

TICKER_UNIVERSE = [
"""

# Group by 10 for readability
for i in range(0, len(symbols), 10):
    batch = symbols[i:i+10]
    line = '    ' + ', '.join(f'"{s}"' for s in batch) + ','
    output += line + '\n'

output += """]

# Sector breakdown (from S&P 500 data)
"""

# Add sector breakdown
sector_counts = sp500_df[sp500_df['Symbol'].isin(symbols)].groupby('GICS Sector').size().sort_values(ascending=False)
output += "# Sector distribution:\n"
for sector, count in sector_counts.items():
    output += f"#   {sector}: {count}\n"

# Save to file
output_file = Path('sp500_ticker_universe.py')
output_file.write_text(output)

print(f"✅ Saved to: {output_file}")

# Also save detailed CSV for reference
sp500_tradable_full = sp500_df[sp500_df['Symbol'].isin(symbols)].merge(
    tradable_df[['symbol', 'name', 'fractionable', 'marginable', 'shortable', 'exchange']], 
    left_on='Symbol', 
    right_on='symbol',
    how='left'
)

sp500_tradable_full = sp500_tradable_full[['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry', 
                                            'exchange', 'fractionable', 'marginable', 'shortable']]
sp500_tradable_full.to_csv('sp500_tradable_details.csv', index=False)
print(f"✅ Saved detailed info to: sp500_tradable_details.csv")

# Print sample
print(f"\n🔍 First 20 symbols:")
for i, sym in enumerate(symbols[:20], 1):
    name = sp500_df[sp500_df['Symbol'] == sym]['Security'].values[0] if len(sp500_df[sp500_df['Symbol'] == sym]) > 0 else ''
    print(f"  {i:2}. {sym:6} - {name[:40]}")

print(f"\n✅ Done! Copy the content from 'sp500_ticker_universe.py' to app/config/settings.py")
print(f"\n📊 Stats:")
print(f"   - S&P 500 constituents: {len(sp500_symbols)}")
print(f"   - Tradable on Alpaca: {len(symbols)}")
print(f"   - Coverage: {len(symbols)/len(sp500_symbols)*100:.1f}%")

# Show which S&P 500 stocks are NOT on Alpaca (if any)
missing = sp500_symbols - set(symbols)
if missing:
    print(f"\n⚠️  {len(missing)} S&P 500 stocks NOT tradable on Alpaca")
    if len(missing) <= 10:
        for sym in sorted(missing):
            print(f"   - {sym}")
    else:
        for sym in sorted(missing)[:10]:
            print(f"   - {sym}")
        print(f"   ... and {len(missing) - 10} more")

