#!/usr/bin/env python3
"""
Backfill 3 years of historical minute bar data for all tickers in TICKER_UNIVERSE

Usage:
    /opt/qtc/venv/bin/python3 backfill_3years.py

Prerequisites:
    - Stop qtc-orchestrator before running
    - Ensure sufficient disk space (~20 GB)
    - Run during off-market hours for better performance

Time estimate: ~30 minutes for 3 years, 538 tickers
"""

import sys
from pathlib import Path
from datetime import date, timedelta
import time

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from app.adapters.ticker_adapter import TickerAdapter
from app.adapters.parquet_writer import ParquetWriter
from app.config.settings import TICKER_UNIVERSE

def is_likely_trading_day(d: date) -> bool:
    """Quick check if date is likely a trading day (excludes weekends)"""
    return d.weekday() < 5  # Monday=0, Friday=4

def main():
    print("=" * 70)
    print("  3-YEAR HISTORICAL DATA BACKFILL")
    print("=" * 70)
    print(f"\n📊 Ticker Universe: {len(TICKER_UNIVERSE)} tickers")
    print(f"   - {len([t for t in TICKER_UNIVERSE if t not in TickerAdapter._CRYPTO_SET])} equities")
    print(f"   - {len([t for t in TICKER_UNIVERSE if t in TickerAdapter._CRYPTO_SET])} crypto")
    
    # Calculate date range (3 years back)
    end_date = date.today()
    start_date = end_date - timedelta(days=3*365)  # ~3 years
    
    # Count potential trading days
    potential_days = 0
    check_date = start_date
    while check_date <= end_date:
        if is_likely_trading_day(check_date):
            potential_days += 1
        check_date += timedelta(days=1)
    
    print(f"\n📅 Date Range: {start_date} to {end_date}")
    print(f"   Potential trading days: ~{potential_days} days")
    print(f"   (Excludes weekends; holidays will have no data)")
    
    # Estimate API calls
    batches_per_day = (len(TICKER_UNIVERSE) + TickerAdapter.BATCH_SIZE - 1) // TickerAdapter.BATCH_SIZE
    estimated_api_calls = potential_days * batches_per_day
    estimated_time_minutes = estimated_api_calls / 150  # Conservative 150 calls/min
    
    print(f"\n⏱️  Estimated:")
    print(f"   API calls: ~{estimated_api_calls:,}")
    print(f"   Time: ~{estimated_time_minutes:.1f} minutes")
    print(f"   Storage: ~16 GB")
    
    # Confirm before proceeding
    print("\n" + "=" * 70)
    response = input("⚠️  Ready to start? Ensure orchestrator is STOPPED! (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("❌ Aborted by user")
        return
    
    print("\n🚀 Starting backfill...\n")
    
    # Track progress
    current_date = start_date
    days_completed = 0
    days_with_data = 0
    total_bars = 0
    errors = 0
    start_time = time.time()
    
    while current_date <= end_date:
        # Skip weekends
        if not is_likely_trading_day(current_date):
            current_date += timedelta(days=1)
            continue
        
        try:
            elapsed = time.time() - start_time
            rate = days_completed / elapsed if elapsed > 0 else 0
            eta_minutes = (potential_days - days_completed) / (rate * 60) if rate > 0 else 0
            
            print(f"📥 [{days_completed+1}/{potential_days}] {current_date} ", end="", flush=True)
            print(f"(ETA: {eta_minutes:.1f}min) ... ", end="", flush=True)
            
            # Fetch data for this day
            bars = TickerAdapter.fetchHistoricalDay(current_date, TICKER_UNIVERSE)
            
            if bars:
                # Write to Parquet
                ParquetWriter.writeDay(bars, root="data/prices/minute_bars")
                print(f"✅ {len(bars):,} bars")
                days_with_data += 1
                total_bars += len(bars)
            else:
                print(f"⚠️  No data (holiday/non-trading day)")
            
            days_completed += 1
            
            # Rate limiting: Stay well under 200/min limit
            # With batching, we're making ~3 calls per day
            # Sleep 0.5s = max 120 days/min = ~360 calls/min (spread over batches)
            # But Alpaca processes batches sequentially, so we're safe
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Interrupted by user")
            print(f"   Completed: {days_completed}/{potential_days} days")
            print(f"   Can resume by running again (will skip existing data)")
            return
        except Exception as e:
            print(f"❌ Error: {e}")
            errors += 1
            if errors > 10:
                print(f"\n❌ Too many errors ({errors}), aborting")
                return
            # Back off on errors
            time.sleep(2)
        
        current_date += timedelta(days=1)
    
    # Final step: Fetch today's data to catch any gaps during backfill
    print("\n" + "=" * 70)
    print("📥 FINAL STEP: Fetching today's data to fill any gaps...")
    print("=" * 70)
    
    today = date.today()
    if is_likely_trading_day(today):
        try:
            print(f"📥 Fetching {today} (complete intraday data)...", end=" ", flush=True)
            today_bars = TickerAdapter.fetchHistoricalDay(today, TICKER_UNIVERSE)
            
            if today_bars:
                ParquetWriter.writeDay(today_bars, root="data/prices/minute_bars")
                print(f"✅ {len(today_bars):,} bars written")
                total_bars += len(today_bars)
                print("   This includes any data from while backfill was running!")
            else:
                print("⚠️  No intraday data available yet")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print(f"⚠️  Today ({today}) is a weekend - skipping")
    
    # Summary
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 70)
    print("✅ BACKFILL COMPLETE!")
    print("=" * 70)
    print(f"📊 Statistics:")
    print(f"   Days processed: {days_completed}")
    print(f"   Days with data: {days_with_data}")
    print(f"   Total bars written: {total_bars:,}")
    print(f"   Errors: {errors}")
    print(f"   Time elapsed: {elapsed_total/60:.1f} minutes")
    print(f"   Average rate: {days_completed/(elapsed_total/60):.1f} days/minute")
    print(f"\n📁 Data location: data/prices/minute_bars/")
    print(f"\n✅ You can now restart the orchestrator:")
    print(f"   sudo systemctl start qtc-orchestrator")
    print(f"   sudo systemctl start qtc-api")
    print(f"\n💡 Today's data was fetched at the end, so minimal gaps!")

if __name__ == "__main__":
    main()

