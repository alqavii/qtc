from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


@dataclass
class AlpacaConfig:
    api_key: str
    api_secret: str
    paper: bool = True


class AlpacaBroker:
    def __init__(self, config: AlpacaConfig) -> None:
        self._client = TradingClient(
            api_key=config.api_key, secret_key=config.api_secret, paper=config.paper
        )

    def placeMarketOrder(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        clientOrderId: Optional[str] = None,
    ) -> str:
        """Submit a market order. Supports fractional qty for eligible assets.

        Alpaca accepts fractional quantities when the account permissions allow it.
        To avoid truncation, send the quantity as a string preserving decimals.
        """
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        qty_str = str(quantity)
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty_str,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        if clientOrderId is not None:
            # alpaca-py MarketOrderRequest supports client_order_id
            setattr(req, "client_order_id", clientOrderId)
        order = self._client.submit_order(order_data=req)
        return str(order.id)

    def getAccountInfo(self) -> dict:
        """Return basic account info including cash and portfolio_value as Decimals (strings converted)."""
        acct = self._client.get_account()
        # alpaca-py returns model fields as strings for numeric values
        return {
            "cash": acct.cash,
            "portfolio_value": getattr(acct, "portfolio_value", None)
            or getattr(acct, "portfolio_value", None),
            "buying_power": getattr(acct, "buying_power", None),
        }

    def getPositions(self) -> list[dict]:
        """Return list of open positions with symbol, qty, side, avg_entry_price, market_value, unrealized_pl."""
        positions = self._client.get_all_positions()
        out: list[dict] = []
        for p in positions:
            out.append(
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "side": p.side,  # 'long' or 'short'
                    "avg_entry_price": p.avg_entry_price,
                    "market_value": getattr(p, "market_value", None),
                    "unrealized_pl": getattr(p, "unrealized_pl", None),
                }
            )
        return out


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env-style file into os.environ (no overwrite)."""
    try:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        # best-effort only
        pass


def _ensure_alpaca_env_loaded() -> None:
    """Best-effort load of alpaca.env from common locations.

    Precedence:
      1) QTC_ALPACA_ENV (absolute path)
      2) /etc/qtc-alpha/alpaca.env (Linux servers)
      3) <repo_root>/etc/qtc-alpha/alpaca.env (dev)
    """
    override = os.getenv("QTC_ALPACA_ENV")
    if override:
        _load_env_file(Path(override))
        return
    sys_path = Path("/etc/qtc-alpha/alpaca.env")
    if sys_path.exists():
        _load_env_file(sys_path)
        return
    repo_root = Path(__file__).resolve().parents[2]
    _load_env_file(repo_root / "etc" / "qtc-alpha" / "alpaca.env")


def load_broker_from_env() -> Optional[AlpacaBroker]:
    _ensure_alpaca_env_loaded()
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    paper = os.getenv("ALPACA_PAPER", "true").lower() in ("1", "true", "yes")
    return AlpacaBroker(AlpacaConfig(api_key=key, api_secret=secret, paper=paper))
