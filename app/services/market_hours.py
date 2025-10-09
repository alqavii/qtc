from __future__ import annotations
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

US_EASTERN = ZoneInfo("America/New_York")

# Simple crypto symbol set. Keep in sync with TickerAdapter._CRYPTO_SET
CRYPTO_SET = {
    "BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "LTC", "BNB", "DOT", "AVAX",
    "LINK", "MATIC", "ATOM", "ARB", "OP", "BCH", "ETC", "NEAR", "APT", "TON",
}


def us_equity_market_open(now_utc: datetime | None = None) -> bool:
    """Return True during regular US market hours (Mon-Fri, 09:30–16:00 ET).

    Simplified: does not include holidays/half-days.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_utc.astimezone(US_EASTERN)
    if now_et.weekday() >= 5:
        return False
    start = time(9, 30)
    end = time(16, 0)
    return start <= now_et.time() < end


def is_symbol_trading(symbol: str, now_utc: datetime | None = None) -> bool:
    s = symbol.upper()
    if s in CRYPTO_SET:
        return True
    return us_equity_market_open(now_utc)

