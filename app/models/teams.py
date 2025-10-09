# models/teams.py
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Optional, Literal, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
from decimal import Decimal


# ----- enums / literals -----
Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
TimeInForce = Literal["day", "gtc", "ioc", "fok"]
OrderStatus = Literal[
    "accepted",
    "new",
    "partially_filled",
    "filled",
    "canceled",
    "expired",
    "rejected",
    "pending_cancel",
]


# --- Strategy ---


class Strategy(BaseModel):
    """Team-attached strategy specification.

    Strategies are provided by users as Python modules stored on disk. The
    loader uses `repoPath` and `entryPoint` to discover and import a class that
    implements a `generate_signal(team, bars, current_prices)` method.

    - repoPath: folder that contains the strategy module file(s)
    - entryPoint: in the form 'filename_without_py:ClassName'
    - params: free-form hyperparameters passed/accessible to user strategies
    """

    name: str = "custom"  # label for UI/logging
    repoPath: Optional[str] = None
    entryPoint: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


# --- Portfolio & Positions ---


class Position(BaseModel):
    symbol: str
    quantity: Decimal  # unsigned
    side: Side  # "buy" = long, "sell" = short
    avgCost: Decimal  # average entry price (per share)
    costBasis: Decimal  # abs(quantity * avgCost)
    openedAt: Optional[datetime] = None

    @classmethod
    def fromTrade(
        cls,
        symbol: str,
        qty: Decimal,
        side: Side,
        price: Decimal,
        ts: Optional[datetime] = None,
    ) -> "Position":
        return cls(
            symbol=symbol,
            quantity=qty,
            side=side,
            avgCost=price,
            costBasis=(abs(qty) * price),
            openedAt=ts or datetime.now(timezone.utc),
        )


class Portfolio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    base: Literal["USD", "GBP", "EUR"] = "USD"

    freeCash: Decimal = Decimal("0")
    positions: Dict[str, Position] = Field(default_factory=dict)  # keyed by ticker

    def positionValue(self, ticker: str, price: Decimal) -> Decimal:
        pos = self.positions.get(ticker)
        return Decimal("0") if pos is None else (pos.quantity * price)

    def grossExposure(self, prices: Dict[str, Decimal]) -> Decimal:
        return Decimal(
            sum(
                abs(self.positionValue(ticker, prices[ticker]))
                for ticker in self.positions
                if ticker in prices
            )
        )

    def netExposure(self, prices: Dict[str, Decimal]) -> Decimal:
        return Decimal(
            sum(
                self.positionValue(ticker, prices[ticker])
                for ticker in self.positions
                if ticker in prices
            )
        )

    def marketValue(self, prices: Dict[str, Decimal]) -> Decimal:
        return self.freeCash + self.netExposure(prices)


class PortfolioValuation(BaseModel):
    as_of: datetime
    baseCurrency: str
    cash: Decimal
    position_values: Dict[str, Decimal]  # symbol -> qty * price
    marketValue: Decimal  # cash + sum(position_values)
    pnlUnrealized: Optional[Decimal] = None
    pnlRealized: Optional[Decimal] = None
    grossExposure: Optional[Decimal] = None


# --- Team ---


class Team(BaseModel):
    teamId: UUID = Field(default_factory=uuid4)
    name: str
    strategy: Strategy
    portfolio: Portfolio

    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
