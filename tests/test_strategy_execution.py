"""
Test strategy execution to verify behavior before and after sandboxing.
"""

import pytest
from pathlib import Path
from decimal import Decimal

# Test data that mimics what the orchestrator provides
SAMPLE_TEAM = {
    "id": "test-team",
    "name": "test-team",
    "cash": 10000.0,
    "positions": {},
    "params": {},
}

SAMPLE_BARS = {
    "AAPL": {
        "timestamp": ["2025-01-01T10:00:00", "2025-01-01T10:01:00"],
        "open": [150.0, 151.0],
        "high": [151.0, 152.0],
        "low": [149.0, 150.0],
        "close": [150.5, 155.0],  # 3% gain to trigger momentum
        "volume": [1000, 1200],
    }
}

SAMPLE_PRICES = {"AAPL": 155.0}


def test_load_strategy_from_fixture():
    """Test that we can load a strategy from the test fixtures."""
    from app.loaders.strategy_loader import load_strategy_from_folder
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = load_strategy_from_folder(fixture_path, "strategy:Strategy")
    
    assert strategy is not None
    assert hasattr(strategy, "generate_signal")


def test_strategy_returns_signal():
    """Test that the strategy returns a valid signal."""
    from app.loaders.strategy_loader import load_strategy_from_folder
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = load_strategy_from_folder(fixture_path, "strategy:Strategy")
    
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    # Should return a buy signal due to 3% momentum
    assert result is not None
    assert result["symbol"] == "AAPL"
    assert result["action"] == "buy"
    assert result["quantity"] == 10


def test_strategy_returns_none_for_no_momentum():
    """Test that strategy returns None when conditions aren't met."""
    from app.loaders.strategy_loader import load_strategy_from_folder
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = load_strategy_from_folder(fixture_path, "strategy:Strategy")
    
    # Bars with no momentum (flat price)
    flat_bars = {
        "AAPL": {
            "timestamp": ["2025-01-01T10:00:00", "2025-01-01T10:01:00"],
            "open": [150.0, 150.0],
            "high": [150.0, 150.0],
            "low": [150.0, 150.0],
            "close": [150.0, 150.0],
            "volume": [1000, 1000],
        }
    }
    
    result = strategy.generate_signal(SAMPLE_TEAM, flat_bars, {"AAPL": 150.0})
    
    assert result is None


def test_strategy_signal_validates():
    """Test that the strategy output validates against StrategySignal model."""
    from app.loaders.strategy_loader import load_strategy_from_folder
    from app.models.trading import StrategySignal
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = load_strategy_from_folder(fixture_path, "strategy:Strategy")
    
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    # Should validate without error (extra fields like "reason" are ignored)
    signal = StrategySignal.model_validate(result)
    assert signal.symbol == "AAPL"
    assert signal.action == "buy"
    assert signal.quantity == Decimal("10")


def test_default_empty_strategy():
    """Test that the default empty strategy returns None."""
    from app.loaders.strategy_loader import get_default_empty_strategy
    
    strategy = get_default_empty_strategy()
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
