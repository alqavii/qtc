from typing import Optional, Dict, Any, Literal

OrderType = Literal["market", "limit"]
TimeInForce = Literal["day", "gtc", "ioc", "fok"]


def make_signal(
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    order_type: OrderType = "market",
    time_in_force: TimeInForce = "day",
) -> Dict[str, Any]:
    """
    Build a trading signal dict that matches StrategySignal schema.
    
    Args:
        symbol: Ticker symbol (e.g., "AAPL", "NVDA")
        action: "buy" or "sell"
        quantity: Number of shares (fractional allowed)
        price: Price for the order (current price for market, limit price for limit orders)
        order_type: "market" (execute immediately) or "limit" (execute at price or better)
        time_in_force: "day" (cancel at end of day), "gtc" (good till cancelled), 
                       "ioc" (immediate or cancel), "fok" (fill or kill)
    
    Returns:
        Dict containing the trading signal matching server's StrategySignal schema
    """
    sig: Dict[str, Any] = {
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "price": price,
        "order_type": order_type,
        "time_in_force": time_in_force,
    }
    return sig


class Strategy:
    """
    Example strategy demonstrating market and limit orders.
    
    Market order (order_type="market"): 
        - Executes immediately at best available price
        - Price field is set to current price for reference
    
    Limit order (order_type="limit"):
        - Executes only at specified price or better
        - Buy limit: Set below current price (e.g., 1% discount)
        - Sell limit: Set above current price (e.g., 1% premium)
    """
    
    def __init__(self, **kwargs):
        self.symbol = "NVDA"
        self.quantity = float(kwargs.get("quantity", 1))
        self._next_action = "buy"
        self.use_limit_orders = False  # Toggle: False for market orders, True for limit orders

    @staticmethod
    def _select_symbol(target: str, bars: dict) -> tuple[str, Optional[dict]]:
        """Find symbol data in bars, with fallback logic."""
        data = bars.get(target)
        if data is not None:
            return target, data
        for key, value in bars.items():
            if "NVDA" in key.upper():
                return key, value
        return target, None

    def generate_signal(self, team: dict, bars: dict, current_prices: dict):
        """
        Generate trading signal based on current market data.
        
        Args:
            team: Team state (cash, positions, api access)
            bars: Historical minute bars per symbol
            current_prices: Latest prices per symbol
        
        Returns:
            Signal dict or None to skip this minute
        """
        symbol, data = self._select_symbol(self.symbol, bars)

        # Get historical closes for fallback
        closes: list[float] = []
        if data:
            closes_raw = data.get("close") or []
            closes = [float(x) for x in closes_raw if x is not None]

        # Get current price (prefer current_prices, fallback to last close)
        price_val = current_prices.get(symbol)
        if price_val is None and closes:
            price_val = closes[-1]
        if price_val is None:
            return None
        current_price = float(price_val)
        if current_price <= 0:
            return None

        # Determine order price and type
        action = self._next_action
        
        if self.use_limit_orders:
            # LIMIT ORDER: Set specific price (may not execute immediately)
            order_type = "limit"
            if action == "buy":
                # Buy limit: Set below current price (e.g., 1% discount)
                order_price = current_price * 0.99
            else:
                # Sell limit: Set above current price (e.g., 1% premium)
                order_price = current_price * 1.01
        else:
            # MARKET ORDER: Use current price (executes immediately at best available)
            order_type = "market"
            order_price = current_price

        # Build and return signal using actual supported fields
        signal = make_signal(
            symbol=symbol,
            action=action,
            quantity=self.quantity,
            price=order_price,
            order_type=order_type,
            time_in_force="day",  # Cancel unfilled orders at end of trading day
        )
        
        # Alternate between buy and sell
        self._next_action = "sell" if action == "buy" else "buy"
        
        return signal
