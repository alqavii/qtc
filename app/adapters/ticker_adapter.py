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
# Support multiple naming conventions
_ALPACA_KEY = (
    os.getenv("ALPACA_API_KEY")
    or os.getenv("ALPACA_KEY")
    or os.getenv("APCA_API_KEY_ID")
)
_ALPACA_SECRET = (
    os.getenv("ALPACA_API_SECRET")
    or os.getenv("ALPACA_SECRET")
    or os.getenv("APCA_API_SECRET_KEY")
)

# Lazy initialization of clients to avoid errors when credentials are not set
_client = None
_crypto_client = None


def _get_client():
    """Get or create the Alpaca stock client."""
    global _client
    if _client is None:
        if _ALPACA_KEY and _ALPACA_SECRET:
            try:
                _client = StockHistoricalDataClient(_ALPACA_KEY, _ALPACA_SECRET)
                print("✓ Alpaca stock client initialized successfully")
            except Exception as e:
                print(f"✗ Error initializing Alpaca stock client: {e}")
                return None
        else:
            print("✗ Alpaca stock client: No credentials available")
    return _client


def _get_crypto_client():
    """Get or create the Alpaca crypto client."""
    global _crypto_client
    if _crypto_client is None:
        if _ALPACA_KEY and _ALPACA_SECRET:
            try:
                _crypto_client = CryptoHistoricalDataClient(_ALPACA_KEY, _ALPACA_SECRET)
                print("✓ Alpaca crypto client initialized successfully")
            except Exception as e:
                print(f"✗ Error initializing Alpaca crypto client: {e}")
                return None
        else:
            print("✗ Alpaca crypto client: No credentials available")
    return _crypto_client


class TickerAdapter:
    """
    Adapter for fetching market data from Alpaca Markets.

    All equity data is fetched from IEX (Investors Exchange) feed to ensure
    consistent pricing from a single exchange source, avoiding SIP data variations.
    """

    # Batch size for API requests (Alpaca limit is ~200 symbols per call)
    BATCH_SIZE = 200

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
            client = _get_client()
            if client:
                try:
                    # Batch equity requests
                    for i in range(0, len(eq), TickerAdapter.BATCH_SIZE):
                        batch = eq[i : i + TickerAdapter.BATCH_SIZE]
                        req = StockLatestBarRequest(symbol_or_symbols=batch, feed="iex")
                        bars = client.get_stock_latest_bar(req)
                        for ticker, bar in bars.items():
                            if bar is None:
                                continue
                            ts = bar.timestamp.astimezone(
                                ZoneInfo("America/New_York")
                            ).replace(second=0, microsecond=0)
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
                except Exception as e:
                    print(f"Error fetching stock bars: {e}")
            else:
                print(
                    "WARNING: Alpaca stock client not initialized - no credentials available"
                )

        if cc:
            crypto_client = _get_crypto_client()
            if crypto_client:
                try:
                    reqc = CryptoLatestBarRequest(
                        symbol_or_symbols=[TickerAdapter._crypto_pair(s) for s in cc]
                    )
                    cbars = crypto_client.get_crypto_latest_bar(reqc)
                    for pair, bar in cbars.items():
                        if bar is None:
                            continue
                        sym = pair.split("/")[0]
                        ts = bar.timestamp.astimezone(
                            ZoneInfo("America/New_York")
                        ).replace(second=0, microsecond=0)
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
                except Exception as e:
                    print(f"Error fetching crypto bars: {e}")
            else:
                print(
                    "WARNING: Alpaca crypto client not initialized - no credentials available"
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
            client = _get_client()
            if client:
                # Batch equity requests
                for i in range(0, len(eq), TickerAdapter.BATCH_SIZE):
                    batch = eq[i : i + TickerAdapter.BATCH_SIZE]
                    req = StockBarsRequest(
                        symbol_or_symbols=batch,
                        timeframe=TimeFrame.Minute,  # type: ignore
                        start=start,
                        end=end,
                        limit=100000,
                        feed="iex",
                    )
                    try:
                        barset = client.get_stock_bars(req)
                    except Exception as e:
                        # Log error but continue with other batches
                        print(
                            f"Warning: Failed to fetch data for batch {batch[:5]}...: {str(e)[:100]}..."
                        )
                        continue

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
            crypto_client = _get_crypto_client()
            if crypto_client:
                reqc = CryptoBarsRequest(
                    symbol_or_symbols=[TickerAdapter._crypto_pair(s) for s in cc],
                    timeframe=TimeFrame.Minute,  # type: ignore
                    start=start,
                    end=end,
                    limit=100000,
                )
                try:
                    cbarset = crypto_client.get_crypto_bars(reqc)
                except Exception as e:
                    # Log error but continue
                    print(f"Warning: Failed to fetch crypto data: {e}")
                    return out

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
