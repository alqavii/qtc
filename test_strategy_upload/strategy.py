# Simple test strategy for single-file upload
import numpy as np

class Strategy:
    def __init__(self, **kwargs):
        self.symbol = kwargs.get('symbol', 'AAPL')
        self.threshold = kwargs.get('threshold', 0.02)
    
    def generate_signal(self, team, bars, current_prices):
        """Simple momentum strategy"""
        if self.symbol not in bars:
            return None
        
        closes = bars[self.symbol].get('close', [])
        if len(closes) < 2:
            return None
        
        # Calculate simple return
        recent_return = (closes[-1] - closes[-2]) / closes[-2]
        
        # Buy on positive momentum
        if recent_return > self.threshold:
            return {
                "symbol": self.symbol,
                "action": "buy",
                "quantity": 10,
                "price": current_prices[self.symbol],
                "reason": f"Momentum: {recent_return:.2%}"
            }
        
        return None

