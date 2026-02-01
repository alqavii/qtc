import importlib.util
import os
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable, cast
from app.models.trading import StrategySignal


# Environment variable to enable sandboxing
# Set QTC_SANDBOX=1 to enable subprocess isolation for strategies
SANDBOX_ENABLED = os.getenv("QTC_SANDBOX", "0") == "1"


@runtime_checkable
class _StrategyProtocol(Protocol):
    def generate_signal(
        self,
        team: dict[str, Any],
        bars: dict[str, Any],
        current_prices: dict[str, float],
    ) -> Optional[dict[str, Any]]: ...


def _load_class_from_file(module_file: Path, class_name: str) -> type[Any]:
    spec = importlib.util.spec_from_file_location(module_file.stem, module_file)
    if spec is None:
        raise ImportError(f"Unable to create module spec for {module_file}")
    mod = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"No loader available for module {module_file}")
    spec.loader.exec_module(mod)
    return cast(type[Any], getattr(mod, class_name))


def load_strategy_from_folder(
    folder: Path | str, entry_point: str, sandbox: Optional[bool] = None
) -> _StrategyProtocol:
    """
    Load a strategy from a folder.
    
    Args:
        folder: Path to team repo folder
        entry_point: 'file_without_py:ClassName' e.g. 'strategy:MeanRevStrategy'
        sandbox: Override sandbox setting (None = use QTC_SANDBOX env var)
    
    Returns:
        Strategy object implementing generate_signal()
    """
    folder = Path(folder)
    file_name, class_name = entry_point.split(":")
    module_file = folder / f"{file_name}.py"
    if not module_file.exists():
        raise FileNotFoundError(f"{module_file} not found in {folder}")

    # Determine if sandboxing is enabled
    use_sandbox = sandbox if sandbox is not None else SANDBOX_ENABLED
    
    if use_sandbox:
        # Use sandboxed execution
        from app.loaders.sandbox import SandboxedStrategy
        strategy: _StrategyProtocol = cast(
            _StrategyProtocol,
            SandboxedStrategy(str(folder), entry_point)
        )
        # Test the sandboxed strategy
        _io_test_strategy(strategy)
        return strategy
    else:
        # Use in-process execution (original behavior)
        StrategyCls = _load_class_from_file(module_file, class_name)
        strategy = cast(_StrategyProtocol, StrategyCls())
        _io_test_strategy(strategy)
        return strategy


def get_default_empty_strategy() -> _StrategyProtocol:
    """
    Returns the default empty strategy that never trades.

    This is used as a fallback when:
    - No strategy is configured for a team
    - Strategy loading fails due to errors
    - Strategy files are missing or corrupted
    """
    # Import the default empty strategy
    default_strategy_path = (
        Path(__file__).parents[2]
        / "external_strategies"
        / "default-empty"
        / "strategy.py"
    )

    if not default_strategy_path.exists():
        # If the default strategy doesn't exist, create a minimal one inline
        class DefaultEmptyStrategy:
            def __init__(self, **kwargs):
                pass

            def generate_signal(self, team, bars, current_prices):
                return None

        return cast(_StrategyProtocol, DefaultEmptyStrategy())

    try:
        StrategyCls = _load_class_from_file(default_strategy_path, "Strategy")
        strategy: _StrategyProtocol = cast(_StrategyProtocol, StrategyCls())
        return strategy
    except Exception:
        # If loading fails, return a minimal inline strategy
        class DefaultEmptyStrategy:
            def __init__(self, **kwargs):
                pass

            def generate_signal(self, team, bars, current_prices):
                return None

        return cast(_StrategyProtocol, DefaultEmptyStrategy())


def _io_test_strategy(strategy: _StrategyProtocol) -> None:
    """Runs generate_signal once with dummy data"""

    team = {"id": "test", "cash": 10000}
    bars = {"AAPL": {"close": [150.0], "volume": [1000]}}
    prices = {"AAPL": 150.0}

    try:
        out = strategy.generate_signal(team, bars, prices)
    except Exception as e:
        raise RuntimeError(
            f"{strategy.__class__.__name__}.generate_signal failed on dummy data: {e}"
        ) from e

    if out is None:
        return  # valid: means no trade

    # Validate with model
    StrategySignal.model_validate(out)
