"""
Simple Example Strategy for QTC Alpha Trading System

This is a basic alternating buy/sell strategy that demonstrates the minimum
required interface for a QTC Alpha strategy.

Features:
- Alternates between buy and sell signals
- Demonstrates proper signal construction
- Shows basic error handling
- Uses the make_signal helper function
"""

from typing import Optional, Dict, Any


def make_signal(
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    confidence: Optional[float] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Helper function to create valid trading signals."""
    signal: Dict[str, Any] = {
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "price": price,
    }
    if confidence is not None:
        signal["confidence"] = float(confidence)
    if reason is not None:
        signal["reason"] = str(reason)
    return signal


class Strategy:
    """
    Simple alternating buy/sell strategy.

    This strategy demonstrates the basic interface required by QTC Alpha.
    It alternates between buying and selling a specified symbol every minute.

    Parameters:
    - symbol: Symbol to trade (default: "NVDA")
    - quantity: Number of shares per trade (default: 1)
    """

    def __init__(self, **kwargs):
        # Strategy parameters
        self.symbol = kwargs.get("symbol", "NVDA")
        self.quantity = float(kwargs.get("quantity", 1))

        # State tracking
        self._next_action = "buy"

        print("Simple Strategy initialized:")
        print(f"  Symbol: {self.symbol}")
        print(f"  Quantity: {self.quantity}")

    @staticmethod
    def _select_symbol(target: str, bars: dict) -> tuple[str, Optional[dict]]:
        """Find the target symbol in available bars data."""
        data = bars.get(target)
        if data is not None:
            return target, data

        # Fallback: look for similar symbol names
        for key, value in bars.items():
            if target.upper() in key.upper():
                return key, value

        return target, None

    def generate_signal(
        self,
        team: Dict[str, Any],
        bars: Dict[str, Any],
        current_prices: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal.

        Args:
            team: Team state including cash, positions, and data API
            bars: Historical minute bars data
            current_prices: Latest prices for all symbols

        Returns:
            Trading signal dict or None if no signal
        """
        try:
            # Find the target symbol in available data
            symbol, data = self._select_symbol(self.symbol, bars)

            # Extract close prices
            closes = []
            if data:
                closes_raw = data.get("close", [])
                closes = [float(x) for x in closes_raw if x is not None]

            # Get current price
            price_val = current_prices.get(symbol)
            if price_val is None and closes:
                price_val = closes[-1]

            if price_val is None or price_val <= 0:
                return None

            price = float(price_val)

            # Generate alternating signal
            action = self._next_action

            signal = make_signal(
                symbol=symbol,
                action=action,
                quantity=self.quantity,
                price=price,
                confidence=0.5,  # Low confidence for demo
                reason=f"Alternating {action} order",
            )

            # Toggle action for next time
            self._next_action = "sell" if action == "buy" else "buy"

            return signal

        except Exception as e:
            # Log error but don't crash the strategy
            print(f"Simple Strategy Error: {e}")
            return None


# Example usage
if __name__ == "__main__":
    # Test the strategy
    strategy = Strategy(symbol="AAPL", quantity=5)

    # Sample team data
    team = {"id": "test-team", "cash": 10000, "positions": {}, "params": {}}

    # Sample bars data
    bars = {
        "AAPL": {
            "close": [150.0, 150.5, 151.0],
            "open": [149.5, 150.0, 150.5],
            "high": [150.2, 150.7, 151.2],
            "low": [149.0, 149.8, 150.3],
            "volume": [1000000, 1100000, 1200000],
        }
    }

    # Sample current prices
    current_prices = {"AAPL": 151.0}

    # Generate signal
    signal = strategy.generate_signal(team, bars, current_prices)
    print(f"Generated signal: {signal}")
