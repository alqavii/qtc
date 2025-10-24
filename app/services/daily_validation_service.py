# daily_validation_service.py
import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from app.adapters.ticker_adapter import TickerAdapter
from app.adapters.parquet_writer import ParquetWriter
from app.config.settings import TICKER_UNIVERSE
from app.services.data_api import StrategyDataAPI

logger = logging.getLogger(__name__)


class DailyValidationService:
    """Daily validation service that checks if price data goes back to 2020 and backfills missing tickers.

    This service runs once per day to ensure all tickers have historical data going back to Jan 1, 2020.
    If any ticker is missing data, it will backfill only that ticker.
    """

    def __init__(self):
        self.data_api = StrategyDataAPI()
        self.target_start_date = date(2020, 1, 1)
        self.last_validation_date: Optional[date] = None
        self.validation_lock = asyncio.Lock()

    async def run_daily_validation(self) -> None:
        """Run daily validation to check and backfill missing historical data."""
        async with self.validation_lock:
            today = date.today()

            # Skip if we already ran validation today
            if self.last_validation_date == today:
                logger.debug("Daily validation already completed today")
                return

            logger.info("Starting daily validation of historical data")

            try:
                missing_tickers = await self._find_missing_tickers()

                if missing_tickers:
                    logger.info(
                        f"Found {len(missing_tickers)} tickers with missing historical data: {missing_tickers}"
                    )
                    await self._backfill_missing_tickers(missing_tickers)
                else:
                    logger.info(
                        "All tickers have complete historical data back to 2020"
                    )

                self.last_validation_date = today
                logger.info("Daily validation completed successfully")

            except Exception as e:
                logger.error(f"Daily validation failed: {e}")

    async def _find_missing_tickers(self) -> List[str]:
        """Find tickers that don't have data going back to 2020."""
        missing_tickers = []

        # Check a sample of dates to see if data exists
        check_dates = [
            self.target_start_date,
            self.target_start_date + timedelta(days=30),
            self.target_start_date + timedelta(days=90),
            self.target_start_date + timedelta(days=180),
            self.target_start_date + timedelta(days=365),
        ]

        for ticker in TICKER_UNIVERSE:
            try:
                # Check if we have data for this ticker on any of the sample dates
                has_data = False
                for check_date in check_dates:
                    try:
                        # Try to get data for this date
                        start_dt = datetime(
                            check_date.year,
                            check_date.month,
                            check_date.day,
                            tzinfo=timezone.utc,
                        )
                        end_dt = start_dt + timedelta(days=1)

                        df = self.data_api.getRange(ticker, start_dt, end_dt)
                        if not df.empty:
                            has_data = True
                            break
                    except Exception:
                        continue

                if not has_data:
                    missing_tickers.append(ticker)

            except Exception as e:
                logger.warning(f"Error checking ticker {ticker}: {e}")
                missing_tickers.append(ticker)

        return missing_tickers

    async def _backfill_missing_tickers(self, missing_tickers: List[str]) -> None:
        """Backfill historical data for missing tickers."""
        logger.info(f"Starting backfill for {len(missing_tickers)} missing tickers")

        # Calculate date range (from 2020 to today)
        end_date = date.today()
        start_date = self.target_start_date

        # Count potential trading days
        potential_days = 0
        check_date = start_date
        while check_date <= end_date:
            if check_date.weekday() < 5:  # Skip weekends
                potential_days += 1
            check_date += timedelta(days=1)

        logger.info(
            f"Backfilling {len(missing_tickers)} tickers over {potential_days} trading days"
        )

        days_completed = 0
        total_bars = 0
        errors = 0

        current_date = start_date
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            try:
                # Fetch data for missing tickers only
                bars = TickerAdapter.fetchHistoricalDay(current_date, missing_tickers)

                if bars:
                    # Write to Parquet (overwrite mode - no duplication)
                    ParquetWriter.writeDay(bars, root="data/prices/minute_bars")
                    total_bars += len(bars)

                days_completed += 1

                # Log progress every 30 days
                if days_completed % 30 == 0:
                    logger.info(
                        f"Backfill progress: {days_completed}/{potential_days} days, {total_bars:,} bars"
                    )

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error backfilling {current_date}: {e}")
                errors += 1
                if errors > 10:
                    logger.error("Too many errors during backfill, stopping")
                    break

            current_date += timedelta(days=1)

        logger.info(
            f"Backfill completed: {days_completed} days, {total_bars:,} bars, {errors} errors"
        )

    async def start_daily_scheduler(self) -> None:
        """Start the daily validation scheduler."""
        logger.info("Starting daily validation scheduler")

        while True:
            try:
                # Run validation at 2 AM UTC (after market close)
                now = datetime.now(timezone.utc)
                next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)

                # If it's already past 2 AM today, schedule for tomorrow
                if now.hour >= 2:
                    next_run += timedelta(days=1)

                # Calculate sleep time
                sleep_seconds = (next_run - now).total_seconds()
                logger.info(f"Next daily validation scheduled for {next_run}")

                await asyncio.sleep(sleep_seconds)
                await self.run_daily_validation()

            except Exception as e:
                logger.error(f"Daily validation scheduler error: {e}")
                # Sleep for 1 hour before retrying
                await asyncio.sleep(3600)


# Global instance
daily_validation_service = DailyValidationService()
