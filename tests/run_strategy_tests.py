#!/usr/bin/env python3
"""
Simple test runner for strategy execution tests.
Run with: python tests/run_strategy_tests.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
    
    assert strategy is not None, "Strategy should not be None"
    assert hasattr(strategy, "generate_signal"), "Strategy should have generate_signal method"
    print("✓ test_load_strategy_from_fixture passed")


def test_strategy_returns_signal():
    """Test that the strategy returns a valid signal."""
    from app.loaders.strategy_loader import load_strategy_from_folder
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = load_strategy_from_folder(fixture_path, "strategy:Strategy")
    
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    # Should return a buy signal due to 3% momentum
    assert result is not None, "Should return a signal for 3% momentum"
    assert result["symbol"] == "AAPL", f"Symbol should be AAPL, got {result['symbol']}"
    assert result["action"] == "buy", f"Action should be buy, got {result['action']}"
    assert result["quantity"] == 10, f"Quantity should be 10, got {result['quantity']}"
    print("✓ test_strategy_returns_signal passed")


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
    
    assert result is None, f"Should return None for flat prices, got {result}"
    print("✓ test_strategy_returns_none_for_no_momentum passed")


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
    print("✓ test_strategy_signal_validates passed")


def test_default_empty_strategy():
    """Test that the default empty strategy returns None."""
    from app.loaders.strategy_loader import get_default_empty_strategy
    
    strategy = get_default_empty_strategy()
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    assert result is None, f"Default strategy should return None, got {result}"
    print("✓ test_default_empty_strategy passed")


def test_sandboxed_strategy_returns_signal():
    """Test that sandboxed strategy returns a valid signal."""
    from app.loaders.sandbox import SandboxedStrategy
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = SandboxedStrategy(str(fixture_path), "strategy:Strategy")
    
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    # Should return a buy signal due to 3% momentum
    assert result is not None, "Sandboxed strategy should return a signal for 3% momentum"
    assert result["symbol"] == "AAPL", f"Symbol should be AAPL, got {result['symbol']}"
    assert result["action"] == "buy", f"Action should be buy, got {result['action']}"
    print("✓ test_sandboxed_strategy_returns_signal passed")


def test_sandboxed_strategy_returns_none():
    """Test that sandboxed strategy returns None when conditions aren't met."""
    from app.loaders.sandbox import SandboxedStrategy
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = SandboxedStrategy(str(fixture_path), "strategy:Strategy")
    
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
    
    assert result is None, f"Sandboxed strategy should return None for flat prices, got {result}"
    print("✓ test_sandboxed_strategy_returns_none passed")


def test_sandboxed_strategy_validates():
    """Test that sandboxed strategy output validates against StrategySignal model."""
    from app.loaders.sandbox import SandboxedStrategy
    from app.models.trading import StrategySignal
    
    fixture_path = Path(__file__).parent / "fixtures"
    strategy = SandboxedStrategy(str(fixture_path), "strategy:Strategy")
    
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    
    # Should validate without error
    signal = StrategySignal.model_validate(result)
    assert signal.symbol == "AAPL"
    assert signal.action == "buy"
    print("✓ test_sandboxed_strategy_validates passed")


def test_load_strategy_with_sandbox_param():
    """Test that load_strategy_from_folder respects sandbox parameter."""
    from app.loaders.strategy_loader import load_strategy_from_folder
    from app.loaders.sandbox import SandboxedStrategy
    
    fixture_path = Path(__file__).parent / "fixtures"
    
    # Load with sandbox=True
    strategy = load_strategy_from_folder(fixture_path, "strategy:Strategy", sandbox=True)
    
    # Should be a SandboxedStrategy instance
    assert isinstance(strategy, SandboxedStrategy), f"Expected SandboxedStrategy, got {type(strategy)}"
    
    # Should still work
    result = strategy.generate_signal(SAMPLE_TEAM, SAMPLE_BARS, SAMPLE_PRICES)
    assert result is not None
    assert result["symbol"] == "AAPL"
    print("✓ test_load_strategy_with_sandbox_param passed")


def test_static_check_scans_all_files():
    """Test that static check scans all .py files in directory."""
    from app.loaders.static_check import ast_sanity_check
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a valid strategy file
        strategy = temp_path / "strategy.py"
        strategy.write_text("""
class Strategy:
    def generate_signal(self, team, bars, prices):
        return None
""")
        
        # Create a helper with blacklisted import
        helper = temp_path / "helper.py"
        helper.write_text("import os\n")
        
        # Should fail because helper.py has blacklisted import
        try:
            ast_sanity_check(temp_path, entry_point="strategy:Strategy")
            assert False, "Should have raised RuntimeError for blacklisted import"
        except RuntimeError as e:
            assert "Blacklisted import: os" in str(e)
    
    print("✓ test_static_check_scans_all_files passed")


def test_static_check_verifies_class_exists():
    """Test that static check verifies Strategy class with generate_signal."""
    from app.loaders.static_check import ast_sanity_check
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create file without Strategy class
        strategy = temp_path / "strategy.py"
        strategy.write_text("x = 1\n")
        
        try:
            ast_sanity_check(temp_path, entry_point="strategy:Strategy")
            assert False, "Should have raised RuntimeError for missing class"
        except RuntimeError as e:
            assert "Class 'Strategy' not found" in str(e)
    
    print("✓ test_static_check_verifies_class_exists passed")


def test_static_check_verifies_generate_signal():
    """Test that static check verifies generate_signal method exists."""
    from app.loaders.static_check import ast_sanity_check
    import tempfile
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create file with class but no generate_signal
        strategy = temp_path / "strategy.py"
        strategy.write_text("""
class Strategy:
    def __init__(self):
        pass
""")
        
        try:
            ast_sanity_check(temp_path, entry_point="strategy:Strategy")
            assert False, "Should have raised RuntimeError for missing method"
        except RuntimeError as e:
            assert "missing 'generate_signal'" in str(e)
    
    print("✓ test_static_check_verifies_generate_signal passed")


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        # Original in-process tests
        test_load_strategy_from_fixture,
        test_strategy_returns_signal,
        test_strategy_returns_none_for_no_momentum,
        test_strategy_signal_validates,
        test_default_empty_strategy,
        # Sandboxed tests
        test_sandboxed_strategy_returns_signal,
        test_sandboxed_strategy_returns_none,
        test_sandboxed_strategy_validates,
        test_load_strategy_with_sandbox_param,
        # Static check tests
        test_static_check_scans_all_files,
        test_static_check_verifies_class_exists,
        test_static_check_verifies_generate_signal,
    ]
    
    passed = 0
    failed = 0
    
    print("\n=== Running Strategy Execution Tests ===\n")
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {type(e).__name__}: {e}")
            failed += 1
    
    print(f"\n=== Results: {passed} passed, {failed} failed ===\n")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
