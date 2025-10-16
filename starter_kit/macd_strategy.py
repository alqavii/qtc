"""
MACD Strategy Example for QTC Alpha Trading System

This is a complete implementation of a MACD (Moving Average Convergence Divergence) strategy
that demonstrates proper error handling, data access, and signal generation.

Features:
- MACD line calculation (12-period EMA - 26-period EMA)
- Signal line calculation (9-period EMA of MACD)
- Histogram calculation (MACD - Signal)
- Bullish/bearish crossover detection
- Proper error handling and data validation
- Configurable parameters
- Risk management integration
"""

import pandas as pd
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


class MACDStrategy:
    """
    MACD (Moving Average Convergence Divergence) Strategy

    This strategy generates buy/sell signals based on MACD line crossovers:
    - Buy when MACD line crosses above signal line (bullish crossover)
    - Sell when MACD line crosses below signal line (bearish crossover)

    Parameters:
    - fast_period: Fast EMA period (default: 12)
    - slow_period: Slow EMA period (default: 26)
    - signal_period: Signal line EMA period (default: 9)
    - symbol: Target symbol to trade (default: "AAPL")
    - quantity: Number of shares per trade (default: 10)
    - min_data_points: Minimum data points required for signal (default: 50)
    """

    def __init__(self, **kwargs):
        # Strategy parameters with defaults
        self.fast_period = kwargs.get("fast_period", 12)
        self.slow_period = kwargs.get("slow_period", 26)
        self.signal_period = kwargs.get("signal_period", 9)
        self.symbol = kwargs.get("symbol", "AAPL")
        self.quantity = kwargs.get("quantity", 10)
        self.min_data_points = kwargs.get("min_data_points", 50)

        # Risk management parameters
        self.max_position_size = kwargs.get(
            "max_position_size", 0.1
        )  # 10% of portfolio
        self.stop_loss_pct = kwargs.get("stop_loss_pct", 0.05)  # 5% stop loss
        self.take_profit_pct = kwargs.get("take_profit_pct", 0.10)  # 10% take profit

        # State tracking
        self.last_signal = None
        self.last_macd = None
        self.last_signal_line = None
        self.position_entry_price = None

        # Validate parameters
        if self.fast_period >= self.slow_period:
            raise ValueError("Fast period must be less than slow period")
        if self.signal_period <= 0:
            raise ValueError("Signal period must be positive")
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")

    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return data.ewm(span=period, adjust=False).mean()

    def calculate_macd(self, prices: pd.Series) -> Dict[str, pd.Series]:
        """
        Calculate MACD components.

        Returns:
        - macd_line: Fast EMA - Slow EMA
        - signal_line: EMA of MACD line
        - histogram: MACD line - Signal line
        """
        if len(prices) < self.slow_period:
            return {
                "macd_line": pd.Series(),
                "signal_line": pd.Series(),
                "histogram": pd.Series(),
            }

        # Calculate EMAs
        fast_ema = self.calculate_ema(prices, self.fast_period)
        slow_ema = self.calculate_ema(prices, self.slow_period)

        # MACD line
        macd_line = fast_ema - slow_ema

        # Signal line (EMA of MACD)
        signal_line = self.calculate_ema(macd_line, self.signal_period)

        # Histogram
        histogram = macd_line - signal_line

        return {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
        }

    def detect_crossover(
        self,
        macd_current: float,
        signal_current: float,
        macd_previous: float,
        signal_previous: float,
    ) -> Optional[str]:
        """
        Detect MACD crossover signals.

        Returns:
        - "bullish": MACD crossed above signal line
        - "bearish": MACD crossed below signal line
        - None: No crossover detected
        """
        if (
            pd.isna(macd_current)
            or pd.isna(signal_current)
            or pd.isna(macd_previous)
            or pd.isna(signal_previous)
        ):
            return None

        # Bullish crossover: MACD was below signal, now above
        if macd_previous <= signal_previous and macd_current > signal_current:
            return "bullish"

        # Bearish crossover: MACD was above signal, now below
        if macd_previous >= signal_previous and macd_current < signal_current:
            return "bearish"

        return None

    def calculate_position_size(
        self, signal: Dict[str, Any], team: Dict[str, Any]
    ) -> float:
        """Calculate appropriate position size based on risk management."""
        portfolio_value = team["cash"]

        # Add current positions to portfolio value
        for position in team["positions"].values():
            portfolio_value += position["quantity"] * position["avg_cost"]

        # Calculate maximum position value
        max_position_value = portfolio_value * self.max_position_size

        # Calculate quantity based on price
        max_quantity = max_position_value / signal["price"]

        # Return minimum of desired quantity and max allowed
        return min(signal["quantity"], max_quantity)

    def check_exit_conditions(
        self, current_price: float, team: Dict[str, Any]
    ) -> Optional[str]:
        """Check if we should exit current position based on stop loss/take profit."""
        if not self.position_entry_price:
            return None

        # Calculate return percentage
        if self.last_signal == "buy":
            return_pct = (
                current_price - self.position_entry_price
            ) / self.position_entry_price
        else:  # short position
            return_pct = (
                self.position_entry_price - current_price
            ) / self.position_entry_price

        # Check stop loss
        if return_pct <= -self.stop_loss_pct:
            return "stop_loss"

        # Check take profit
        if return_pct >= self.take_profit_pct:
            return "take_profit"

        return None

    def generate_signal(
        self,
        team: Dict[str, Any],
        bars: Dict[str, Any],
        current_prices: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal based on MACD analysis.

        Args:
            team: Team state including cash, positions, and data API
            bars: Historical minute bars data
            current_prices: Latest prices for all symbols

        Returns:
            Trading signal dict or None if no signal
        """
        try:
            # Get data for target symbol
            symbol_data = bars.get(self.symbol)
            if not symbol_data:
                return None

            # Extract close prices
            closes = symbol_data.get("close", [])
            if not closes or len(closes) < self.min_data_points:
                return None

            # Convert to pandas Series
            prices = pd.Series(closes)

            # Calculate MACD components
            macd_data = self.calculate_macd(prices)
            macd_line = macd_data["macd_line"]
            signal_line = macd_data["signal_line"]

            if macd_line.empty or signal_line.empty:
                return None

            # Get current and previous values
            macd_current = macd_line.iloc[-1]
            signal_current = signal_line.iloc[-1]

            if len(macd_line) < 2:
                return None

            macd_previous = macd_line.iloc[-2]
            signal_previous = signal_line.iloc[-2]

            # Get current price
            current_price = current_prices.get(self.symbol)
            if not current_price or current_price <= 0:
                return None

            # Check exit conditions first
            exit_reason = self.check_exit_conditions(current_price, team)
            if exit_reason:
                action = "sell" if self.last_signal == "buy" else "buy"
                signal = make_signal(
                    symbol=self.symbol,
                    action=action,
                    quantity=self.quantity,
                    price=current_price,
                    confidence=0.9,
                    reason=f"Exit: {exit_reason}",
                )
                self.last_signal = None
                self.position_entry_price = None
                return signal

            # Detect crossover
            crossover = self.detect_crossover(
                macd_current, signal_current, macd_previous, signal_previous
            )

            if not crossover:
                return None

            # Generate signal based on crossover
            if crossover == "bullish" and self.last_signal != "buy":
                action = "buy"
                confidence = min(
                    0.8, abs(macd_current - signal_current) / abs(signal_current) + 0.5
                )
                reason = "MACD bullish crossover"

            elif crossover == "bearish" and self.last_signal != "sell":
                action = "sell"
                confidence = min(
                    0.8, abs(macd_current - signal_current) / abs(signal_current) + 0.5
                )
                reason = "MACD bearish crossover"

            else:
                return None

            # Create signal
            signal = make_signal(
                symbol=self.symbol,
                action=action,
                quantity=self.quantity,
                price=current_price,
                confidence=confidence,
                reason=reason,
            )

            # Calculate appropriate position size
            signal["quantity"] = self.calculate_position_size(signal, team)

            # Update state
            self.last_signal = action
            self.last_macd = macd_current
            self.last_signal_line = signal_current

            if action == "buy":
                self.position_entry_price = current_price

            return signal

        except Exception as e:
            # Log error but don't crash the strategy
            print(f"MACD Strategy Error: {e}")
            return None


# Main Strategy class (required interface)
class Strategy(MACDStrategy):
    """
    Main Strategy class that implements the required interface.

    This is the entry point that the QTC Alpha system will instantiate.
    All configuration should be done through the constructor parameters.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Log strategy initialization
        print("MACD Strategy initialized:")
        print(f"  Symbol: {self.symbol}")
        print(f"  Fast Period: {self.fast_period}")
        print(f"  Slow Period: {self.slow_period}")
        print(f"  Signal Period: {self.signal_period}")
        print(f"  Quantity: {self.quantity}")
        print(f"  Max Position Size: {self.max_position_size * 100}%")
        print(f"  Stop Loss: {self.stop_loss_pct * 100}%")
        print(f"  Take Profit: {self.take_profit_pct * 100}%")


# Example usage and testing
if __name__ == "__main__":
    # Test the strategy with sample data
    strategy = Strategy(
        symbol="AAPL", fast_period=12, slow_period=26, signal_period=9, quantity=10
    )

    # Sample data
    sample_prices = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    macd_data = strategy.calculate_macd(sample_prices)

    print("Sample MACD calculation:")
    print(f"MACD Line: {macd_data['macd_line'].iloc[-1]:.4f}")
    print(f"Signal Line: {macd_data['signal_line'].iloc[-1]:.4f}")
    print(f"Histogram: {macd_data['histogram'].iloc[-1]:.4f}")
