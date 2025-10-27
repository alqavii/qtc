# minute_service.py
import asyncio
import inspect
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Iterable, List, Optional
from datetime import date

from app.models.ticker_data import MinuteBar

logger = logging.getLogger(__name__)


class MinuteClock:
    """Lightweight minute-aligned scheduler.

    Registers callables that will be invoked at the start of each minute
    (UTC-aligned). Handlers may be sync or async and receive the tick timestamp.
    """

    def __init__(self) -> None:
        self._handlers: List[Callable[[datetime], object]] = []
        self._stop = asyncio.Event()

    def register(self, fn: Callable[[datetime], object]) -> None:
        self._handlers.append(fn)

    async def run(self) -> None:
        while not self._stop.is_set():
            now = datetime.now(timezone.utc)
            nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            await asyncio.sleep(max(0.0, (nxt - now).total_seconds()) + 0.05)
            await self._tick(nxt)

    async def _tick(self, as_of: datetime) -> None:
        tasks: List[Awaitable[object]] = []
        for fn in self._handlers:
            if inspect.iscoroutinefunction(fn):
                tasks.append(fn(as_of))
            else:
                tasks.append(asyncio.to_thread(fn, as_of))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("[minute-clock] handler error: %s", r)

    async def stop(self) -> None:
        self._stop.set()


class MinuteService:
    """Fetches market data on minute ticks and writes/dispatches results.

    Args:
        fetch: Callable that returns an iterable of MinuteBar. May be sync or async.
        write: Callable that persists a batch of MinuteBar. May be sync or async.
        post_hook: Optional callable run after write with the same bars list.
                  Useful for downstream strategy execution. May be sync or async.
    """

    def __init__(
        self,
        *,
        fetch: Callable[[], Iterable[MinuteBar]]
        | Callable[[], Awaitable[Iterable[MinuteBar]]],
        write: Callable[[Iterable[MinuteBar]], object]
        | Callable[[Iterable[MinuteBar]], Awaitable[object]],
        post_hook: Optional[
            Callable[[List[MinuteBar]], object]
            | Callable[[List[MinuteBar]], Awaitable[object]]
        ] = None,
        # Optional daily backfill/fix of previous day
        historical_fetch_day: Optional[
            Callable[[date], Iterable[MinuteBar]]
            | Callable[[date], Awaitable[Iterable[MinuteBar]]]
        ] = None,
        write_day: Optional[
            Callable[[Iterable[MinuteBar]], object]
            | Callable[[Iterable[MinuteBar]], Awaitable[object]]
        ] = None,
    ) -> None:
        self._fetch = fetch
        self._write = write
        self._post = post_hook
        self._historical_fetch_day = historical_fetch_day
        self._write_day = write_day
        self._clock = MinuteClock()
        self._task: Optional[asyncio.Task[None]] = None
        self._last_fix_day: Optional[date] = None

        # Register the per-minute handler
        self._clock.register(self._on_minute)

    async def _call(self, fn, *args):
        if inspect.iscoroutinefunction(fn):
            return await fn(*args)
        return await asyncio.to_thread(fn, *args)

    async def _on_minute(self, as_of: datetime) -> None:
        try:
            # Fetch latest bars
            logger.debug(f"Fetching bars for {as_of}")
            bars_iter = await self._call(self._fetch)
            bars: List[MinuteBar] = list(bars_iter or [])
            logger.debug(f"Fetched {len(bars)} bars")
            if not bars:
                # No fresh data; attempt fallback
                try:
                    if (
                        self._historical_fetch_day is not None
                        and self._write_day is not None
                    ):
                        today = as_of.date()
                        hist_iter = await self._call(self._historical_fetch_day, today)
                        hist_bars: List[MinuteBar] = list(hist_iter or [])
                        if hist_bars:
                            await self._call(self._write_day, hist_bars)
                except Exception as exc:
                    logger.warning("Minute fallback fetch failed: %s", exc)

                # STILL call post_hook with empty list - orchestrator needs to update portfolios even with stale data
                if self._post is not None:
                    logger.debug(
                        f"Calling post_hook with {len(bars)} bars (no new data)"
                    )
                    await self._call(self._post, [])
                return

            # Ensure all timestamps align to the tick minute
            for b in bars:
                b.timestamp = b.timestamp.replace(
                    second=0, microsecond=0, tzinfo=timezone.utc
                )

            # Persist
            await self._call(self._write, bars)
            logger.debug(f"Persisted {len(bars)} bars to parquet")

            # Optional downstream hook
            if self._post is not None:
                await self._call(self._post, bars)
                logger.debug(f"Triggered post_hook with {len(bars)} bars")

            # Daily backfill of previous day once per UTC day
            if self._historical_fetch_day is not None and self._write_day is not None:
                today = as_of.date()
                if self._last_fix_day is None or self._last_fix_day != today:
                    prev = today - timedelta(days=1)
                    try:
                        hist_iter = await self._call(self._historical_fetch_day, prev)
                        hist_bars: List[MinuteBar] = list(hist_iter or [])
                        if hist_bars:
                            await self._call(self._write_day, hist_bars)
                            self._last_fix_day = today
                    except Exception:
                        logger.exception("[minute-service] daily fix error")
        except Exception:
            logger.exception("[minute-service] error during minute tick")

    async def run(self) -> None:
        # Kick an immediate fetch/write on start so users see data without waiting
        await self._on_minute(
            datetime.now(timezone.utc).replace(second=0, microsecond=0)
        )
        await self._clock.run()

    async def stop(self) -> None:
        await self._clock.stop()
