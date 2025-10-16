from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
import yfinance as yf
from typing import List, Tuple

from app.models.ticker_data import MinuteBar, TickerMetadata, InstrumentSnapshot
from app.config.settings import TICKER_UNIVERSE
from app.adapters.alpaca_broker import _ensure_alpaca_env_loaded

from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import (
    StockLatestBarRequest,
    StockBarsRequest,
    CryptoLatestBarRequest,
    CryptoBarsRequest,
)
from alpaca.data.timeframe import TimeFrame
import os

_ensure_alpaca_env_loaded()
_ALPACA_KEY = os.getenv("ALPACA_API_KEY")
_ALPACA_SECRET = os.getenv("ALPACA_API_SECRET")
client = StockHistoricalDataClient(_ALPACA_KEY, _ALPACA_SECRET)
crypto_client = CryptoHistoricalDataClient(_ALPACA_KEY, _ALPACA_SECRET)


class TickerAdapter:
    """
    Adapter for fetching market data from Alpaca Markets.

    All equity data is fetched from IEX (Investors Exchange) feed to ensure
    consistent pricing from a single exchange source, avoiding SIP data variations.
    """

    _CRYPTO_SET = {
        "BTC",
        "ETH",
        "SOL",
        "DOGE",
        "XRP",
        "ADA",
        "LTC",
        "BNB",
        "DOT",
        "AVAX",
        "LINK",
        "MATIC",
        "ATOM",
        "ARB",
        "OP",
        "BCH",
        "ETC",
        "NEAR",
        "APT",
        "TON",
    }

    @staticmethod
    def _split_crypto(tickers: List[str]) -> Tuple[List[str], List[str]]:
        eq: List[str] = []
        cc: List[str] = []
        for t in tickers:
            s = t.upper()
            if s in TickerAdapter._CRYPTO_SET:
                cc.append(s)
            else:
                eq.append(s)
        return eq, cc

    @staticmethod
    def _crypto_pair(sym: str) -> str:
        return f"{sym}/USD"

    @staticmethod
    def fetchBasic(tickers: List[str] = TICKER_UNIVERSE) -> list[MinuteBar]:
        eq, cc = TickerAdapter._split_crypto(list(tickers))
        out: list[MinuteBar] = []

        if eq:
            req = StockLatestBarRequest(symbol_or_symbols=eq, feed="iex")
            bars = client.get_stock_latest_bar(req)
            for ticker, bar in bars.items():
                if bar is None:
                    continue
                ts = bar.timestamp.astimezone(ZoneInfo("America/New_York")).replace(
                    second=0, microsecond=0
                )
                out.append(
                    MinuteBar(
                        ticker=ticker,
                        timestamp=ts,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=None,
                        tradeCount=None,
                        vwap=None,
                        asOf=datetime.now(timezone.utc),
                    )
                )

        if cc:
            reqc = CryptoLatestBarRequest(
                symbol_or_symbols=[TickerAdapter._crypto_pair(s) for s in cc]
            )
            cbars = crypto_client.get_crypto_latest_bar(reqc)
            for pair, bar in cbars.items():
                if bar is None:
                    continue
                sym = pair.split("/")[0]
                ts = bar.timestamp.astimezone(ZoneInfo("America/New_York")).replace(
                    second=0, microsecond=0
                )
                out.append(
                    MinuteBar(
                        ticker=sym,
                        timestamp=ts,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=getattr(bar, "volume", None),
                        tradeCount=getattr(bar, "trade_count", None),
                        vwap=getattr(bar, "vwap", None),
                        asOf=datetime.now(timezone.utc),
                    )
                )

        return out

    @staticmethod
    def fetchFull(ticker: str) -> list[object]:
        stock = yf.Ticker(ticker)

        TickerMetadataModel = TickerMetadata(ticker=ticker)

        TickerMetadataModel.companyName = stock.info.get("longName", "N/A")
        TickerMetadataModel.sector = stock.info.get("sector", "N/A")
        TickerMetadataModel.industry = stock.info.get("industry", "N/A")
        TickerMetadataModel.marketCap = stock.info.get("marketCap", "N/A")
        TickerMetadataModel.exchange = stock.info.get("exchange", "N/A")

        InstrumentSnapshotModel = InstrumentSnapshot(ticker=ticker)
        InstrumentSnapshotModel.marketCap = stock.info.get("marketCap", "N/A")
        InstrumentSnapshotModel.yearHigh = stock.info.get("fiftyTwoWeekHigh", "N/A")
        InstrumentSnapshotModel.yearLow = stock.info.get("fiftyTwoWeekLow", "N/A")
        InstrumentSnapshotModel.dividendYield = stock.info.get("dividendYield", "N/A")

        return [TickerMetadataModel, InstrumentSnapshotModel]

    @staticmethod
    def fetchHistoricalDay(
        day: date | datetime, tickers: List[str] = TICKER_UNIVERSE
    ) -> list[MinuteBar]:
        if isinstance(day, datetime):
            d0 = day.date()
        else:
            d0 = day

        eastern = ZoneInfo("America/New_York")
        start = datetime(d0.year, d0.month, d0.day, 0, 0, tzinfo=eastern)
        end = start + timedelta(days=1)

        eq, cc = TickerAdapter._split_crypto(list(tickers))
        out: list[MinuteBar] = []

        if eq:
            req = StockBarsRequest(
                symbol_or_symbols=eq,
                timeframe=TimeFrame.Minute,  # type: ignore
                start=start,
                end=end,
                limit=100000,
                feed="iex",
            )
            barset = client.get_stock_bars(req)

            def _iter_stock_groups(obj):
                if hasattr(obj, "items"):
                    return obj.items()
                data = getattr(obj, "data", obj)
                groups = {}
                for b in data:
                    sym = getattr(b, "symbol", None)
                    if sym is None:
                        continue
                    groups.setdefault(str(sym), []).append(b)
                return groups.items()

            for symbol, series in _iter_stock_groups(barset):
                if not series:
                    continue
                for bar in series:
                    ts = bar.timestamp.astimezone(eastern).replace(
                        second=0, microsecond=0
                    )
                    out.append(
                        MinuteBar(
                            ticker=symbol,
                            timestamp=ts,
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=getattr(bar, "volume", None),
                            tradeCount=getattr(bar, "trade_count", None),
                            vwap=getattr(bar, "vwap", None),
                            asOf=datetime.now(timezone.utc),
                        )
                    )

        if cc:
            reqc = CryptoBarsRequest(
                symbol_or_symbols=[TickerAdapter._crypto_pair(s) for s in cc],
                timeframe=TimeFrame.Minute,  # type: ignore
                start=start,
                end=end,
                limit=100000,
            )
            cbarset = crypto_client.get_crypto_bars(reqc)

            def _iter_crypto_groups(obj):
                if hasattr(obj, "items"):
                    return obj.items()
                data = getattr(obj, "data", obj)
                groups = {}
                for b in data:
                    sym = getattr(b, "symbol", None)
                    if sym is None:
                        continue
                    s = str(sym)
                    if "/" in s:
                        s = s.split("/")[0]
                    groups.setdefault(s, []).append(b)
                return groups.items()

            for pair, series in _iter_crypto_groups(cbarset):
                if not series:
                    continue
                sym = (
                    pair.split("/")[0]
                    if isinstance(pair, str) and "/" in pair
                    else str(pair)
                )
                for bar in series:
                    ts = bar.timestamp.astimezone(eastern).replace(
                        second=0, microsecond=0
                    )
                    out.append(
                        MinuteBar(
                            ticker=sym,
                            timestamp=ts,
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=getattr(bar, "volume", None),
                            tradeCount=getattr(bar, "trade_count", None),
                            vwap=getattr(bar, "vwap", None),
                            asOf=datetime.now(timezone.utc),
                        )
                    )

        out.sort(key=lambda b: (b.timestamp, b.ticker))
        return out
