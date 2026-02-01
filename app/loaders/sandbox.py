"""
Subprocess-based sandbox for executing untrusted strategy code.

Provides process isolation with resource limits:
- Memory limit (256 MB default)
- CPU time limit (5 seconds default)
- No network access (blocked at Python level)
- No file creation
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default resource limits
DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_MEMORY_MB = 256

# Path to the sandbox runner script
RUNNER_SCRIPT = Path(__file__).parent / "sandbox_runner.py"


def run_strategy_sandboxed(
    strategy_path: str,
    entry_point: str,
    team_data: Dict[str, Any],
    bars: Dict[str, Any],
    prices: Dict[str, float],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> Optional[Dict[str, Any]]:
    """
    Execute a strategy in an isolated subprocess with resource limits.
    
    Args:
        strategy_path: Path to directory containing strategy files
        entry_point: Entry point in format "file:ClassName" (e.g., "strategy:Strategy")
        team_data: Team information dict (id, name, cash, positions, params)
        bars: Market data dict (symbol -> OHLCV arrays)
        prices: Current prices dict (symbol -> price)
        timeout: Maximum execution time in seconds
        memory_mb: Maximum memory usage in MB
    
    Returns:
        Signal dict if strategy returns a trade signal, None otherwise
    
    Raises:
        TimeoutError: If strategy exceeds time limit
        RuntimeError: If strategy crashes or returns invalid data
    """
    # Remove api reference from team_data (can't serialize)
    team_clean = {k: v for k, v in team_data.items() if k != "api"}
    
    # Prepare input data
    input_data = {
        "strategy_path": str(strategy_path),
        "entry_point": entry_point,
        "team": team_clean,
        "bars": bars,
        "prices": prices,
        "memory_mb": memory_mb,
    }
    
    try:
        # Run the sandbox runner as a subprocess
        result = subprocess.run(
            [sys.executable, str(RUNNER_SCRIPT)],
            input=json.dumps(input_data),
            capture_output=True,
            timeout=timeout,
            text=True,
            # Don't inherit environment to reduce attack surface
            env={
                "PATH": "",
                "PYTHONPATH": str(Path(__file__).parents[2]),
            },
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            logger.warning(f"Sandbox execution failed: {error_msg}")
            raise RuntimeError(f"Strategy execution failed: {error_msg}")
        
        # Parse output
        output = result.stdout.strip()
        if not output or output == "null":
            return None
        
        try:
            signal = json.loads(output)
            return signal
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON output from strategy: {e}")
            
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Strategy exceeded {timeout}s time limit")
    except FileNotFoundError:
        raise RuntimeError(f"Sandbox runner not found at {RUNNER_SCRIPT}")


class SandboxedStrategy:
    """
    Wrapper that provides the same interface as regular strategies
    but executes in a sandboxed subprocess.
    """
    
    def __init__(
        self,
        strategy_path: str,
        entry_point: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        memory_mb: int = DEFAULT_MEMORY_MB,
    ):
        self.strategy_path = strategy_path
        self.entry_point = entry_point
        self.timeout = timeout
        self.memory_mb = memory_mb
        self._class_name = entry_point.split(":")[-1] if ":" in entry_point else "Strategy"
    
    @property
    def __class__(self):
        """Return a mock class for logging purposes."""
        class _MockClass:
            pass
        _MockClass.__name__ = f"Sandboxed:{self._class_name}"
        return _MockClass
    
    def generate_signal(
        self,
        team: Dict[str, Any],
        bars: Dict[str, Any],
        current_prices: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the strategy in a sandbox and return the signal.
        
        Matches the _StrategyProtocol interface.
        """
        return run_strategy_sandboxed(
            strategy_path=self.strategy_path,
            entry_point=self.entry_point,
            team_data=team,
            bars=bars,
            prices=current_prices,
            timeout=self.timeout,
            memory_mb=self.memory_mb,
        )
