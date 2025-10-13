# Technical indicators module
import numpy as np

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    if len(prices) < period + 1:
        return 50.0  # Neutral
    
    prices_array = np.array(prices)
    deltas = np.diff(prices_array)
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

