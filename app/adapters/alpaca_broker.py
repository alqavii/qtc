from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus


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

    def placeLimitOrder(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        limit_price: Decimal,
        time_in_force: str = "day",
        clientOrderId: Optional[str] = None,
    ) -> str:
        """Submit a limit order at specified price.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            side: 'buy' or 'sell'
            quantity: Quantity to trade (supports fractional shares)
            limit_price: Maximum price for buy, minimum price for sell
            time_in_force: 'day', 'gtc', 'ioc', 'fok' (default: 'day')
            clientOrderId: Optional client-provided order ID
            
        Returns:
            Alpaca order ID as string
        """
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        qty_str = str(quantity)
        limit_price_str = str(limit_price)
        
        # Map time_in_force string to enum
        tif_map = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
        }
        tif = tif_map.get(time_in_force.lower(), TimeInForce.DAY)
        
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty_str,
            side=order_side,
            time_in_force=tif,
            limit_price=limit_price_str,
        )
        if clientOrderId is not None:
            setattr(req, "client_order_id", clientOrderId)
        
        order = self._client.submit_order(order_data=req)
        return str(order.id)

    def getOrderById(self, order_id: str) -> dict:
        """Get order details by order ID.
        
        Args:
            order_id: Alpaca order ID
            
        Returns:
            Dictionary with order details including:
            - id: Order ID
            - symbol: Stock symbol
            - qty: Ordered quantity
            - filled_qty: Quantity filled so far
            - side: 'buy' or 'sell'
            - type: Order type ('market', 'limit', etc.)
            - status: Order status ('filled', 'partially_filled', 'pending', etc.)
            - filled_avg_price: Average execution price (None if not filled)
            - limit_price: Limit price (for limit orders)
            - created_at: Order creation timestamp
            - filled_at: Fill timestamp (None if not filled)
            - client_order_id: Client-provided order ID
        """
        order = self._client.get_order_by_id(order_id)
        return {
            "id": str(order.id),
            "client_order_id": getattr(order, "client_order_id", None),
            "symbol": order.symbol,
            "qty": order.qty,
            "filled_qty": getattr(order, "filled_qty", None),
            "side": order.side.value if hasattr(order.side, "value") else str(order.side),
            "type": order.type.value if hasattr(order.type, "value") else str(order.type),
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "filled_avg_price": getattr(order, "filled_avg_price", None),
            "limit_price": getattr(order, "limit_price", None),
            "created_at": order.created_at,
            "filled_at": getattr(order, "filled_at", None),
        }

    def getAllOrders(self, status: str = "open") -> list[dict]:
        """Get all orders with specified status.
        
        Args:
            status: Order status filter - "open", "closed", "all"
                   - "open": pending, new, partially_filled, accepted
                   - "closed": filled, cancelled, expired, rejected
                   - "all": all orders
        
        Returns:
            List of order dictionaries with details
        """
        # Map string status to QueryOrderStatus enum
        status_map = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL,
        }
        
        query_status = status_map.get(status.lower(), QueryOrderStatus.OPEN)
        
        # Create request for orders
        request = GetOrdersRequest(status=query_status, limit=500)
        orders = self._client.get_orders(filter=request)
        
        result = []
        for order in orders:
            result.append({
                "id": str(order.id),
                "client_order_id": getattr(order, "client_order_id", None),
                "symbol": order.symbol,
                "qty": order.qty,
                "filled_qty": getattr(order, "filled_qty", None),
                "side": order.side.value if hasattr(order.side, "value") else str(order.side),
                "type": order.type.value if hasattr(order.type, "value") else str(order.type),
                "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                "filled_avg_price": getattr(order, "filled_avg_price", None),
                "limit_price": getattr(order, "limit_price", None),
                "time_in_force": order.time_in_force.value if hasattr(order.time_in_force, "value") else str(order.time_in_force),
                "created_at": order.created_at,
                "updated_at": getattr(order, "updated_at", None),
                "submitted_at": getattr(order, "submitted_at", None),
                "filled_at": getattr(order, "filled_at", None),
                "expired_at": getattr(order, "expired_at", None),
                "cancelled_at": getattr(order, "cancelled_at", None),
            })
        
        return result

    def cancelOrder(self, order_id: str) -> dict:
        """Cancel an open order.
        
        Args:
            order_id: Alpaca order ID
            
        Returns:
            Dictionary with cancellation status
        """
        try:
            self._client.cancel_order_by_id(order_id)
            return {
                "success": True,
                "order_id": order_id,
                "message": "Order cancelled successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "order_id": order_id,
                "error": str(e)
            }


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
