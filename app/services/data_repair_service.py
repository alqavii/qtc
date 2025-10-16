# data_repair_service.py
import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional
from pathlib import Path
from collections import deque

from app.adapters.ticker_adapter import TickerAdapter
from app.adapters.parquet_writer import ParquetWriter
from app.services.market_hours import us_equity_market_open, is_symbol_trading
from app.config.settings import TICKER_UNIVERSE

logger = logging.getLogger(__name__)


# Non-blocking logging for data repair service
class NonBlockingLogger:
    """A non-blocking logger that queues log messages to prevent blocking journalctl."""

    def __init__(self, name: str, max_queue_size: int = 1000):
        self.logger = logging.getLogger(name)
        self.queue = deque(maxlen=max_queue_size)
        self.lock = threading.Lock()
        self._worker_thread = None
        self._shutdown = False

    def _start_worker(self):
        """Start the background worker thread for processing log messages."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(
                target=self._process_queue, daemon=True
            )
            self._worker_thread.start()

    def _process_queue(self):
        """Process queued log messages in a separate thread."""
        while not self._shutdown:
            try:
                with self.lock:
                    if not self.queue:
                        continue
                    level, message, args, kwargs = self.queue.popleft()

                # Log the message without blocking
                getattr(self.logger, level)(message, *args, **kwargs)

            except Exception:
                # If logging fails, just continue to prevent blocking
                pass

    def info(self, message, *args, **kwargs):
        """Queue an info level log message."""
        self._start_worker()
        with self.lock:
            self.queue.append(("info", message, args, kwargs))

    def debug(self, message, *args, **kwargs):
        """Queue a debug level log message."""
        self._start_worker()
        with self.lock:
            self.queue.append(("debug", message, args, kwargs))

    def warning(self, message, *args, **kwargs):
        """Queue a warning level log message."""
        self._start_worker()
        with self.lock:
            self.queue.append(("warning", message, args, kwargs))

    def error(self, message, *args, **kwargs):
        """Queue an error level log message."""
        self._start_worker()
        with self.lock:
            self.queue.append(("error", message, args, kwargs))

    def exception(self, message, *args, **kwargs):
        """Queue an exception level log message."""
        self._start_worker()
        with self.lock:
            self.queue.append(("exception", message, args, kwargs))


# Use non-blocking logger for data repair service
data_repair_logger = NonBlockingLogger(__name__)


class DataRepairService:
    """Asynchronous data repair service that scans for missing ticker/minute data and patches gaps.

    Features:
    - 15-minute intervals during market hours (9:30 AM - 4:00 PM ET)
    - 60-minute intervals during off-hours
    - Idempotent operations (no duplication or overwriting)
    - Comprehensive gap detection and repair
    - Async operation to avoid blocking main trading loop
    """

    def __init__(self, root: str = "data/prices/minute_bars"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_repair_time: Optional[datetime] = None

    async def start(self) -> None:
        """Start the data repair service."""
        if self._running:
            data_repair_logger.warning("Data repair service is already running")
            return

        data_repair_logger.info("Starting data repair service...")
        self._running = True
        self._task = asyncio.create_task(self._repair_loop())

    async def stop(self) -> None:
        """Stop the data repair service."""
        if not self._running:
            return

        data_repair_logger.info("Stopping data repair service...")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        data_repair_logger.info("Data repair service stopped")

    async def _repair_loop(self) -> None:
        """Main repair loop that runs at different intervals based on market hours."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                market_open = us_equity_market_open(now)

                # Determine repair interval based on market hours
                if market_open:
                    interval_minutes = 15
                    # Only log interval changes, not every cycle
                    if (
                        not hasattr(self, "_last_market_state")
                        or self._last_market_state != "open"
                    ):
                        data_repair_logger.info(
                            "Market hours: using 15-minute repair interval"
                        )
                        self._last_market_state = "open"
                else:
                    interval_minutes = 60
                    # Only log interval changes, not every cycle
                    if (
                        not hasattr(self, "_last_market_state")
                        or self._last_market_state != "closed"
                    ):
                        data_repair_logger.info(
                            "Off-hours: using 60-minute repair interval"
                        )
                        self._last_market_state = "closed"

                # Perform repair
                await self._perform_repair(now)

                # Wait for next interval
                await asyncio.sleep(interval_minutes * 60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                data_repair_logger.exception(f"Error in data repair loop: {e}")
                # Wait a bit before retrying to avoid rapid error loops
                await asyncio.sleep(60)

    async def _perform_repair(self, as_of: datetime) -> None:
        """Perform comprehensive data repair for all symbols."""
        try:
            # Only log repair start occasionally to avoid spam
            if (
                not hasattr(self, "_last_repair_start_log")
                or (as_of - self._last_repair_start_log).total_seconds() > 1800
            ):  # Log once every 30 minutes
                data_repair_logger.info(f"Starting data repair at {as_of.isoformat()}")
                self._last_repair_start_log = as_of

            # Get all symbols that should be trading
            trading_symbols = self._get_trading_symbols(as_of)

            if not trading_symbols:
                data_repair_logger.debug("No symbols to repair")
                return

            # Check for gaps in recent data
            gaps_found = 0
            repairs_made = 0
            symbols_with_gaps = []

            for symbol in trading_symbols:
                try:
                    gaps = await self._detect_gaps(symbol, as_of)
                    if gaps:
                        gaps_found += len(gaps)
                        repaired = await self._repair_gaps(symbol, gaps)
                        repairs_made += repaired
                        if repaired > 0:
                            symbols_with_gaps.append(f"{symbol}({repaired})")
                except Exception as e:
                    data_repair_logger.warning(f"Failed to repair {symbol}: {e}")

            self._last_repair_time = as_of

            # Only log summary if there were repairs, and limit frequency
            if repairs_made > 0:
                # Only log if we haven't logged repairs recently
                if (
                    not hasattr(self, "_last_repair_log")
                    or (as_of - self._last_repair_log).total_seconds() > 300
                ):  # Log at most every 5 minutes
                    data_repair_logger.info(
                        f"Data repair completed: {repairs_made} gaps repaired across {len(symbols_with_gaps)} symbols"
                    )
                    # Log symbols with repairs only if there are very few of them
                    if len(symbols_with_gaps) <= 3:
                        data_repair_logger.info(
                            f"Repaired symbols: {', '.join(symbols_with_gaps)}"
                        )
                    self._last_repair_log = as_of
            else:
                # Only log "no gaps" very occasionally to avoid spam
                if (
                    not hasattr(self, "_last_no_gaps_log")
                    or (as_of - self._last_no_gaps_log).total_seconds() > 7200
                ):  # Log once every 2 hours
                    data_repair_logger.debug("Data repair completed: no gaps found")
                    self._last_no_gaps_log = as_of

        except Exception as e:
            data_repair_logger.exception(f"Error during data repair: {e}")

    def _get_trading_symbols(self, as_of: datetime) -> Set[str]:
        """Get all symbols that should be trading at the given time."""
        trading_symbols = set()

        for symbol in TICKER_UNIVERSE:
            if is_symbol_trading(symbol, as_of):
                trading_symbols.add(symbol)

        return trading_symbols

    async def _detect_gaps(self, symbol: str, as_of: datetime) -> List[datetime]:
        """Detect missing minute bars for a symbol in the recent time window."""
        gaps = []

        try:
            # Look back 2 hours for gap detection during market hours
            # Look back 24 hours during off-hours
            market_open = us_equity_market_open(as_of)
            lookback_hours = 2 if market_open else 24

            start_time = as_of - timedelta(hours=lookback_hours)

            # Get existing data for the symbol
            existing_data = await self._get_existing_data(symbol, start_time, as_of)
            existing_timestamps = {row["timestamp"] for row in existing_data}

            # Generate expected timestamps
            expected_timestamps = self._generate_expected_timestamps(
                symbol, start_time, as_of
            )

            # Find missing timestamps
            for expected_ts in expected_timestamps:
                if expected_ts not in existing_timestamps:
                    gaps.append(expected_ts)

        except Exception as e:
            data_repair_logger.warning(f"Error detecting gaps for {symbol}: {e}")

        return gaps

    async def _get_existing_data(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[dict]:
        """Get existing minute bar data for a symbol from parquet files."""
        try:
            from app.services.data_api import StrategyDataAPI

            api = StrategyDataAPI()
            df = api.getRange(symbol, start, end)

            if df.empty:
                return []

            return df.to_dict("records")

        except Exception as e:
            data_repair_logger.debug(f"No existing data found for {symbol}: {e}")
            return []

    def _generate_expected_timestamps(
        self, symbol: str, start: datetime, end: datetime
    ) -> List[datetime]:
        """Generate expected minute timestamps for a symbol based on trading hours."""
        expected_timestamps = []

        # Convert to Eastern time for market hours calculation
        eastern = timezone.utc
        try:
            from zoneinfo import ZoneInfo

            eastern = ZoneInfo("America/New_York")
        except ImportError:
            pass

        current = start.replace(second=0, microsecond=0)

        while current < end:
            # Check if this timestamp should have data for this symbol
            if is_symbol_trading(symbol, current):
                expected_timestamps.append(current)

            current += timedelta(minutes=1)

        return expected_timestamps

    async def _repair_gaps(self, symbol: str, gaps: List[datetime]) -> int:
        """Repair missing data gaps for a symbol."""
        if not gaps:
            return 0

        repaired_count = 0

        try:
            # Group gaps by date for efficient fetching
            gaps_by_date = {}
            for gap_time in gaps:
                gap_date = gap_time.date()
                if gap_date not in gaps_by_date:
                    gaps_by_date[gap_date] = []
                gaps_by_date[gap_date].append(gap_time)

            # Fetch and write data for each date
            for gap_date, gap_times in gaps_by_date.items():
                try:
                    # Fetch historical data for the entire day
                    bars = TickerAdapter.fetchHistoricalDay(gap_date, [symbol])

                    if bars:
                        # Filter to only the missing timestamps
                        missing_bars = []
                        gap_times_set = set(gap_times)

                        for bar in bars:
                            bar_time = bar.timestamp.replace(second=0, microsecond=0)
                            if bar_time in gap_times_set:
                                missing_bars.append(bar)

                        if missing_bars:
                            # Write the missing bars (idempotent operation)
                            ParquetWriter.writeDay(missing_bars, root=str(self.root))
                            repaired_count += len(missing_bars)
                            # Only log individual repairs at debug level and very rarely
                            if (
                                not hasattr(self, "_last_individual_repair_log")
                                or (gap_date - self._last_individual_repair_log).days
                                > 0
                            ):
                                data_repair_logger.debug(
                                    f"Repaired {len(missing_bars)} bars for {symbol} on {gap_date}"
                                )
                                self._last_individual_repair_log = gap_date

                except Exception as e:
                    data_repair_logger.warning(
                        f"Failed to repair gaps for {symbol} on {gap_date}: {e}"
                    )

        except Exception as e:
            data_repair_logger.warning(f"Error repairing gaps for {symbol}: {e}")

        return repaired_count

    def get_status(self) -> dict:
        """Get current status of the data repair service."""
        return {
            "running": self._running,
            "last_repair_time": self._last_repair_time.isoformat()
            if self._last_repair_time
            else None,
            "root_path": str(self.root),
            "symbols_tracked": len(TICKER_UNIVERSE),
        }


# Global instance for use throughout the application
data_repair_service = DataRepairService()
