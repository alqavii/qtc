from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import pyarrow.dataset as ds
from app.adapters.ticker_adapter import TickerAdapter
from app.adapters.parquet_writer import ParquetWriter
from app.config.settings import TICKER_UNIVERSE


@dataclass
class StrategyDataAPI:
    """
    Read-only helper to access stored minute bar data written in Parquet.

    Exposes simple methods safe to call from user strategies (no writes).
    """

    # Preferred location for parquet minute bars
    root: Path = Path("data/prices/minute_bars")

    def _ensure_today_backfill(self, symbol: str) -> None:
        """Ensure today's minute bars for symbol exist by fetching and writing.

        Also adds the symbol to the in-memory universe if not present.
        """
        sym = symbol.upper()
        if sym not in TICKER_UNIVERSE:
            try:
                TICKER_UNIVERSE.append(sym)
            except Exception:
                pass
        today = datetime.now(timezone.utc).date()
        bars = TickerAdapter.fetchHistoricalDay(today, [sym])
        if bars:
            ParquetWriter.writeDay(bars, root=str(self.root))

    def _dataset(self) -> ds.Dataset:
        # Backward-compat: if new root missing but old exists, read from old
        preferred = self.root
        legacy = Path("app/data/minute_bars")
        base = preferred if preferred.exists() else (legacy if legacy.exists() else preferred)
        return ds.dataset(base, format="parquet", partitioning="hive")

    def getRange(self, symbol: str | List[str], start: datetime, end: datetime) -> pd.DataFrame | Dict[str, pd.DataFrame]:
        """Return rows for [start, end).

        - str -> DataFrame
        - list[str] -> dict[symbol, DataFrame]
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # Multi-symbol path
        if not isinstance(symbol, str):
            symbols = [s.upper() for s in symbol]
            if not symbols:
                return {}
            dset = self._dataset()
            filt = (
                (ds.field("ticker").isin(symbols))
                & (ds.field("timestamp") >= pd.Timestamp(start))
                & (ds.field("timestamp") < pd.Timestamp(end))
            )
            try:
                table = dset.to_table(filter=filt)
            except Exception:
                for sym in symbols:
                    self._ensure_today_backfill(sym)
                dset = self._dataset()
                table = dset.to_table(filter=filt)
            df = table.to_pandas()
            out: Dict[str, pd.DataFrame] = {}
            for sym in symbols:
                sdf = df[df["ticker"] == sym].copy()
                if sdf.empty and end.date() == datetime.now(timezone.utc).date():
                    self._ensure_today_backfill(sym)
                    dset = self._dataset()
                    table = dset.to_table(filter=filt)
                    df = table.to_pandas()
                    sdf = df[df["ticker"] == sym].copy()
                out[sym] = sdf.reset_index(drop=True)
            return out

        dset = self._dataset()
        filt = (
            (ds.field("ticker") == symbol.upper())
            & (ds.field("timestamp") >= pd.Timestamp(start))
            & (ds.field("timestamp") < pd.Timestamp(end))
        )
        try:
            table = dset.to_table(filter=filt)
        except Exception:
            # dataset missing; try backfill for today then re-open
            self._ensure_today_backfill(symbol.upper())
            dset = self._dataset()
            table = dset.to_table(filter=filt)
        df = table.to_pandas()
        if df.empty and end.date() == datetime.now(timezone.utc).date():
            self._ensure_today_backfill(symbol.upper())
            dset = self._dataset()
            table = dset.to_table(filter=filt)
            df = table.to_pandas()
        return df

    def getDay(self, symbol: str | List[str], day: date) -> pd.DataFrame | Dict[str, pd.DataFrame]:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return self.getRange(symbol, start, end)

    def getLastN(self, symbol: str | List[str], n: int) -> pd.DataFrame | Dict[str, pd.DataFrame]:
        """Return last n rows for symbol(s) across all stored partitions.

        - str -> DataFrame
        - list[str] -> dict[symbol, DataFrame]
        """
        if n <= 0:
            return {} if not isinstance(symbol, str) else pd.DataFrame()
        if not isinstance(symbol, str):
            out: Dict[str, pd.DataFrame] = {}
            for sym in symbol:
                out[sym.upper()] = self.getLastN(sym, n)  # type: ignore[assignment]
            return out
        # Read recent partitions first by scanning partition dirs by date
        sym = symbol.upper()
        if not self.root.exists():
            self._ensure_today_backfill(sym)
            if not self.root.exists():
                return pd.DataFrame()

        # Collect files sorted desc by date using partition naming y=.../m=.../d=...
        files: List[Path] = sorted(self.root.rglob("*.parquet"), reverse=True)
        frames: List[pd.DataFrame] = []
        remaining = n
        for fp in files:
            try:
                df = pd.read_parquet(fp)
                if "ticker" not in df.columns:
                    continue
                sdf = df[df["ticker"] == sym]
                if not sdf.empty:
                    frames.append(sdf)
                    remaining -= len(sdf)
                    if remaining <= 0:
                        break
            except Exception:
                continue
        if not frames:
            self._ensure_today_backfill(sym)
            files = sorted(self.root.rglob("*.parquet"), reverse=True)
            for fp in files:
                try:
                    df = pd.read_parquet(fp)
                    if "ticker" not in df.columns:
                        continue
                    sdf = df[df["ticker"] == sym]
                    if not sdf.empty:
                        frames.append(sdf)
                        break
                except Exception:
                    continue
            if not frames:
                return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values("timestamp").tail(n)
        return out.reset_index(drop=True)

    # ---- multi-symbol helpers ----
    def getRangeMulti(self, symbols: list[str], start: datetime, end: datetime) -> dict[str, pd.DataFrame]:
        """Return DataFrames per symbol for [start, end)."""
        if not symbols:
            return {}
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        dset = self._dataset()
        filt = (
            (ds.field("ticker").isin(symbols))
            & (ds.field("timestamp") >= pd.Timestamp(start))
            & (ds.field("timestamp") < pd.Timestamp(end))
        )
        table = dset.to_table(filter=filt)
        df = table.to_pandas()
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            sdf = df[df["ticker"] == sym].copy()
            out[sym] = sdf.reset_index(drop=True)
        return out

    def getDayMulti(self, symbols: list[str], day: date) -> dict[str, pd.DataFrame]:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return self.getRangeMulti(symbols, start, end)

    def getLastNMulti(self, symbols: list[str], n: int) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            out[sym] = self.getLastN(sym, n)
        return out
