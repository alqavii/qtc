# Risk management module

class RiskManager:
    def __init__(self, max_position=0.10):
        self.max_position = max_position
    
    def calculate_position_size(self, cash, price):
        """Calculate position size based on available cash and risk limits"""
        max_dollar_amount = cash * self.max_position
        shares = int(max_dollar_amount / price)
        return max(1, shares)  # At least 1 share
    
    def check_position_limit(self, current_positions, symbol, max_positions=10):
        """Check if we can add another position"""
        if symbol in current_positions:
            return True  # Can add to existing position
        return len(current_positions) < max_positions

