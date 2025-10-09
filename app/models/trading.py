from __future__ import annotations
from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Optional, Literal
from decimal import Decimal
from datetime import datetime, timezone

Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
TimeInForce = Literal["day", "gtc", "ioc", "fok"]


class StrategySignal(BaseModel):
    symbol: str
    action: Side
    quantity: Decimal
    price: Decimal
    confidence: Optional[float] = None
    reason: Optional[str] = None


class TradeRequest(BaseModel):
    team_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    order_type: OrderType = "market"
    time_in_force: TimeInForce = "day"
    clientOrderId: Optional[str] = None


class TradeRecord(BaseModel):
    team_id: str
    symbol: str
    side: Side
    quantity: Decimal
    requested_price: Decimal
    execution_price: Decimal
    order_type: OrderType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    broker_order_id: Optional[str] = None


class PositionView(BaseModel):
    symbol: str
    quantity: Decimal
    side: Side
    avg_cost: Decimal
    value: Decimal
    pnl_unrealized: Optional[Decimal] = None


class PortfolioSnapshot(BaseModel):
    team_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cash: Decimal
    positions: Dict[str, PositionView]
    market_value: Decimal
