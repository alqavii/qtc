# Multi-file test strategy
from indicators import calculate_rsi
from risk_manager import RiskManager
import config

class Strategy:
    def __init__(self, **kwargs):
        self.risk_manager = RiskManager(max_position=config.MAX_POSITION_SIZE)
        self.rsi_period = kwargs.get('rsi_period', 14)
    
    def generate_signal(self, team, bars, current_prices):
        """RSI-based strategy using helper modules"""
        symbol = "AAPL"
        
        if symbol not in bars:
            return None
        
        closes = bars[symbol].get('close', [])
        if len(closes) < self.rsi_period + 1:
            return None
        
        # Calculate RSI using helper function
        rsi = calculate_rsi(closes, self.rsi_period)
        
        # Buy when oversold
        if rsi < config.RSI_OVERSOLD:
            quantity = self.risk_manager.calculate_position_size(
                team['cash'], 
                current_prices[symbol]
            )
            
            return {
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "price": current_prices[symbol],
                "reason": f"RSI oversold: {rsi:.1f}"
            }
        
        # Sell when overbought
        elif rsi > config.RSI_OVERBOUGHT:
            return {
                "symbol": symbol,
                "action": "sell",
                "quantity": 10,
                "price": current_prices[symbol],
                "reason": f"RSI overbought: {rsi:.1f}"
            }
        
        return None

