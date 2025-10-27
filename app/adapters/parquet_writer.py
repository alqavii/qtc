from __future__ import annotations
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo
import pandas as pd

from app.models.ticker_data import MinuteBar


class ParquetWriter:
    def __init__(self, root: str = "data/prices/minute_bars") -> None:
        self.root = Path(root)

    def append(self, bars: Iterable[MinuteBar]) -> None:
        bars = list(bars)
        if not bars:
            return
        recs = [b.model_dump() for b in bars]
        df = pd.DataFrame(recs)
        # Preserve timezone info; compute Eastern day for file selection
        df["timestamp"] = pd.to_datetime(df["timestamp"])  # keep tz if present
        ts0 = pd.to_datetime(df["timestamp"].iloc[0])
        eastern = ZoneInfo("America/New_York")
        if ts0.tzinfo is not None:
            try:
                ts_local = ts0.tz_convert(eastern)
            except Exception:
                ts_local = ts0
        else:
            ts_local = ts0
        y, m, d = ts_local.year, ts_local.month, ts_local.day
        outdir = self.root / f"y={y}" / f"m={m}" / f"d={d}"
        outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / f"minute_bars-{y}-{m:02d}-{d:02d}.parquet"

        # Idempotent append: check for existing data to prevent duplication
        if outpath.exists():
            try:
                existing_df = pd.read_parquet(outpath)
                if not existing_df.empty:
                    # Create composite key for deduplication
                    existing_df["composite_key"] = (
                        existing_df["ticker"]
                        + "_"
                        + existing_df["timestamp"].astype(str)
                    )
                    df["composite_key"] = (
                        df["ticker"] + "_" + df["timestamp"].astype(str)
                    )

                    # Filter out duplicates
                    new_bars = df[
                        ~df["composite_key"].isin(existing_df["composite_key"])
                    ]
                    if new_bars.empty:
                        return  # No new data to append
                    df = new_bars.drop("composite_key", axis=1)
            except Exception:
                # If we can't read existing file, proceed with append
                pass

        # Append new data (or create file if it doesn't exist)
        if not df.empty:
            if outpath.exists():
                df.to_parquet(
                    outpath,
                    engine="fastparquet",
                    compression="snappy",
                    append=True,
                    index=False,
                )
            else:
                # File doesn't exist, create it without append mode
                df.to_parquet(
                    outpath,
                    engine="fastparquet",
                    compression="snappy",
                    append=False,
                    index=False,
                )

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
            self._day = None
            self._schema = None
            self._path = None

    @staticmethod
    def appendParquet(
        bars: Iterable[MinuteBar], root: str = "data/prices/minute_bars"
    ) -> None:
        appendParquet(bars, root)

    @staticmethod
    def writeDay(
        bars: Iterable[MinuteBar], root: str = "data/prices/minute_bars"
    ) -> None:
        bars = list(bars)
        if not bars:
            return
        recs = [b.model_dump() for b in bars]
        df = pd.DataFrame(recs)
        df["timestamp"] = pd.to_datetime(df["timestamp"])  # preserve tz if present
        ts0 = pd.to_datetime(df["timestamp"].iloc[0])
        eastern = ZoneInfo("America/New_York")
        if ts0.tzinfo is not None:
            try:
                ts_local = ts0.tz_convert(eastern)
            except Exception:
                ts_local = ts0
        else:
            ts_local = ts0
        y, m, d = ts_local.year, ts_local.month, ts_local.day
        outdir = Path(root) / f"y={y}" / f"m={m}" / f"d={d}"
        outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / f"minute_bars-{y}-{m:02d}-{d:02d}.parquet"

        # Idempotent write: check for existing data to prevent duplication
        if outpath.exists():
            try:
                existing_df = pd.read_parquet(outpath)
                if not existing_df.empty:
                    # Create composite key for deduplication
                    existing_df["composite_key"] = (
                        existing_df["ticker"]
                        + "_"
                        + existing_df["timestamp"].astype(str)
                    )
                    df["composite_key"] = (
                        df["ticker"] + "_" + df["timestamp"].astype(str)
                    )

                    # Filter out duplicates
                    new_bars = df[
                        ~df["composite_key"].isin(existing_df["composite_key"])
                    ]
                    if new_bars.empty:
                        return  # No new data to write
                    df = new_bars.drop("composite_key", axis=1)
            except Exception:
                # If we can't read existing file, proceed with write
                pass

        # Write new data (or create file if it doesn't exist)
        if not df.empty:
            if outpath.exists():
                df.to_parquet(
                    outpath,
                    engine="fastparquet",
                    compression="snappy",
                    append=True,
                    index=False,
                )
            else:
                # File doesn't exist, create it without append mode
                df.to_parquet(
                    outpath,
                    engine="fastparquet",
                    compression="snappy",
                    append=False,
                    index=False,
                )


# Simple module-level facade to match legacy usage


def appendParquet(
    bars: Iterable[MinuteBar], root: str = "data/prices/minute_bars"
) -> None:
    # No persistent writer needed; use append-to-file semantics
    ParquetWriter(root).append(bars)
