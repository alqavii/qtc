from pydantic import BaseModel, Field
from typing import Optional
from zoneinfo import ZoneInfo
from decimal import Decimal
from datetime import datetime, timezone


class MinuteBar(BaseModel):
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    # Some crypto venues report fractional volume; accept float
    volume: Optional[float] = None
    tradeCount: Optional[int] = None
    vwap: Optional[float] = None
    asOf: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TickerMetadata(BaseModel):
    ticker: str
    companyName: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    marketCap: Optional[float] = None
    timezone: Optional[ZoneInfo] = None
    exchange: Optional[str] = None

    asOf: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstrumentSnapshot(BaseModel):
    ticker: str
    marketCap: Optional[float] = None
    yearHigh: Optional[float] = None
    yearLow: Optional[float] = None
    dividendYield: Optional[Decimal] = None

    asOf: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
