import importlib.util
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable, cast
from app.models.trading import StrategySignal


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
    folder: Path | str, entry_point: str
) -> _StrategyProtocol:
    """
    folder: path to team repo folder
    entry_point: 'file_without_py:ClassName' e.g. 'strategy:MeanRevStrategy'
    """
    folder = Path(folder)
    file_name, class_name = entry_point.split(":")
    module_file = folder / f"{file_name}.py"
    if not module_file.exists():
        raise FileNotFoundError(f"{module_file} not found in {folder}")

    StrategyCls = _load_class_from_file(module_file, class_name)
    strategy: _StrategyProtocol = cast(_StrategyProtocol, StrategyCls())

    _io_test_strategy(strategy)

    return strategy


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
