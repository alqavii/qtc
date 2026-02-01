"""
Shared dependencies for API routers.

Contains helper functions and shared instances used across multiple routers.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone

from app.config.environments import config


def tail_jsonl(path: Path) -> Optional[Dict[str, Any]]:
    """Read the last valid JSON line from a JSONL file."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read = min(16384, size)
            f.seek(size - read)
            chunk = f.read().decode("utf-8", errors="ignore")
            lines = [ln for ln in chunk.splitlines() if ln.strip()]
            for ln in reversed(lines):
                try:
                    return json.loads(ln)
                except Exception:
                    continue
    except Exception:
        return None
    return None


def list_team_ids() -> List[str]:
    """Get list of all team IDs from the data directory."""
    root = config.get_data_path("team")
    if not root.exists():
        return []
    return [p.name for p in root.iterdir() if p.is_dir()]


def calculate_performance_metrics(
    history: List[Dict[str, Any]], initial_value: Optional[float] = None
) -> Dict[str, Any]:
    """Calculate performance metrics from portfolio history.

    Args:
        history: List of portfolio snapshots with 'timestamp' and 'value'
        initial_value: Optional starting portfolio value (uses first value if not provided)

    Returns:
        Dictionary containing Sharpe, Sortino, Calmar ratios, drawdowns, returns, etc.
    """
    if len(history) < 2:
        return {
            "error": "Insufficient data for metrics calculation",
            "data_points": len(history),
        }

    try:
        import numpy as np

        # Extract values and timestamps, filtering out invalid entries
        valid_history = []
        for h in history:
            try:
                # Validate timestamp
                ts_str = h.get("timestamp", "")
                if not ts_str or ts_str == "NaT" or "NaT" in str(ts_str):
                    continue

                # Validate value
                value = h.get("value")
                if value is None:
                    continue

                # Parse timestamp to ensure it's valid
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

                # Add to valid history
                valid_history.append({"timestamp": ts, "value": float(value)})
            except (ValueError, TypeError, AttributeError):
                # Skip invalid entries
                continue

        if len(valid_history) < 2:
            return {
                "error": "Insufficient valid data for metrics calculation",
                "data_points": len(history),
                "valid_data_points": len(valid_history),
            }

        # Extract values and timestamps from validated data
        values = np.array([h["value"] for h in valid_history])
        timestamps = [h["timestamp"] for h in valid_history]

        # Handle edge case: all zero values
        if np.all(values == 0):
            return {
                "error": "All portfolio values are zero",
                "data_points": len(history),
            }

        # Calculate returns, handling division by zero
        with np.errstate(divide="ignore", invalid="ignore"):
            returns = np.diff(values) / values[:-1]

        # Filter out invalid returns (inf, -inf, nan)
        valid_returns = returns[np.isfinite(returns)]

        if len(valid_returns) < 2:
            return {
                "error": "Insufficient valid returns for metrics calculation",
                "data_points": len(history),
                "valid_returns": len(valid_returns),
            }

        # Use valid returns for calculations
        returns = valid_returns

        # Time period analysis
        time_diff = (timestamps[-1] - timestamps[0]).total_seconds()
        days_elapsed = max(time_diff / 86400, 0.001)  # Avoid zero
        years_elapsed = days_elapsed / 365.25

        # Assume minute-level data for annualization
        # Trading days: 252, Trading minutes per day: 390 (6.5 hours)
        periods_per_year = 252 * 390

        # Mean return and volatility
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)

        # Handle edge case: zero or near-zero volatility (constant portfolio value)
        min_volatility = 1e-10
        if std_return < min_volatility:
            # Portfolio is essentially constant
            annualized_return = (
                mean_return * periods_per_year if years_elapsed > 0 else 0
            )
            annualized_volatility = 0.0
            sharpe_ratio = (
                0.0
                if abs(annualized_return) < 1e-10
                else (np.inf if annualized_return > 0 else -np.inf)
            )
            sortino_ratio = 0.0
        else:
            # Normal calculations
            annualized_return = (
                mean_return * periods_per_year if years_elapsed > 0 else 0
            )
            annualized_volatility = std_return * np.sqrt(periods_per_year)

            # Sharpe Ratio (assuming risk-free rate = 0 for simplicity)
            sharpe_ratio = annualized_return / annualized_volatility

            # Sortino Ratio (only downside volatility)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 1:
                downside_std = np.std(downside_returns, ddof=1)
                if downside_std < min_volatility:
                    # No downside volatility (only gains)
                    sortino_ratio = np.inf if annualized_return > 0 else 0.0
                else:
                    annualized_downside_vol = downside_std * np.sqrt(periods_per_year)
                    sortino_ratio = annualized_return / annualized_downside_vol
            else:
                # No or insufficient downside moves
                sortino_ratio = np.inf if annualized_return > 0 else 0.0

        # Drawdown analysis
        cumulative_max = np.maximum.accumulate(values)

        # Handle division by zero in drawdown calculation
        with np.errstate(divide="ignore", invalid="ignore"):
            drawdowns = (values - cumulative_max) / cumulative_max

        # Replace inf/nan with 0 (can happen if cumulative_max is 0)
        drawdowns = np.nan_to_num(drawdowns, nan=0.0, posinf=0.0, neginf=0.0)

        max_drawdown = float(np.min(drawdowns))

        # Find max drawdown period
        max_dd_idx = np.argmin(drawdowns)
        max_dd_value = float(values[max_dd_idx])
        max_dd_peak = float(cumulative_max[max_dd_idx])

        # Current drawdown
        current_drawdown = float(drawdowns[-1])

        # Calmar Ratio (annualized return / max drawdown)
        if abs(max_drawdown) < 1e-10:
            # No drawdown (perfect performance or flat)
            if abs(annualized_return) < 1e-10:
                calmar_ratio = 0.0
            else:
                calmar_ratio = np.inf if annualized_return > 0 else -np.inf
        else:
            calmar_ratio = annualized_return / abs(max_drawdown)

        # Total return
        start_value = initial_value if initial_value else values[0]
        end_value = values[-1]

        # Handle zero starting value
        if abs(start_value) < 1e-10:
            if abs(end_value) < 1e-10:
                total_return = 0.0
            else:
                # Started from 0, gained value
                total_return = np.inf if end_value > 0 else -np.inf
        else:
            total_return = (end_value - start_value) / start_value

        total_return_percentage = (
            total_return * 100 if np.isfinite(total_return) else total_return
        )

        # Average win/loss
        winning_returns = returns[returns > 0]
        losing_returns = returns[returns < 0]
        avg_win = float(np.mean(winning_returns)) if len(winning_returns) > 0 else 0
        avg_loss = float(np.mean(losing_returns)) if len(losing_returns) > 0 else 0

        # Helper function to convert inf to None for JSON serialization
        def safe_float(value):
            """Convert value to float, replacing inf with None for JSON compatibility."""
            if np.isinf(value):
                return None  # JSON-friendly representation
            if np.isnan(value):
                return None
            return float(value)

        return {
            "sharpe_ratio": safe_float(sharpe_ratio),
            "sortino_ratio": safe_float(sortino_ratio),
            "calmar_ratio": safe_float(calmar_ratio),
            "max_drawdown": safe_float(max_drawdown),
            "max_drawdown_percentage": safe_float(max_drawdown * 100),
            "current_drawdown": safe_float(current_drawdown),
            "current_drawdown_percentage": safe_float(current_drawdown * 100),
            "total_return": safe_float(total_return),
            "total_return_percentage": safe_float(total_return_percentage),
            "annualized_return": safe_float(annualized_return),
            "annualized_return_percentage": safe_float(annualized_return * 100),
            "annualized_volatility": safe_float(annualized_volatility),
            "annualized_volatility_percentage": safe_float(annualized_volatility * 100),
            "avg_win": safe_float(avg_win),
            "avg_loss": safe_float(avg_loss),
            "total_trades": int(len(returns)),
            "winning_trades": int(len(winning_returns)),
            "losing_trades": int(len(losing_returns)),
            "current_value": safe_float(end_value),
            "starting_value": safe_float(start_value),
            "peak_value": safe_float(np.max(values)),
            "trough_value": safe_float(np.min(values)),
            "max_drawdown_details": {
                "peak_value": safe_float(max_dd_peak),
                "trough_value": safe_float(max_dd_value),
                "drawdown_amount": safe_float(max_dd_peak - max_dd_value),
            },
            "period": {
                "start": timestamps[0].isoformat(),
                "end": timestamps[-1].isoformat(),
                "days": float(days_elapsed),
                "data_points": len(history),
            },
        }

    except Exception as e:
        return {
            "error": f"Metrics calculation failed: {str(e)}",
            "data_points": len(history),
        }


def read_portfolio_history(
    team_id: str, days: Optional[int] = None, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Read historical portfolio data from both parquet and JSONL files.

    Args:
        team_id: Team identifier
        days: Number of days to look back (None = all available)
        limit: Maximum number of data points to return (None = all)

    Returns:
        List of portfolio snapshots with timestamp and market_value
    """
    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"

    if not port_dir.exists():
        return []

    history: List[Dict[str, Any]] = []
    cutoff_time = None

    if days is not None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

    # Read from Parquet files (historical data)
    try:
        import pandas as pd

        parquet_files = sorted(port_dir.glob("*.parquet"))
        for pf in parquet_files:
            try:
                df = pd.read_parquet(pf)
                if "timestamp" in df.columns and "market_value" in df.columns:
                    for _, row in df.iterrows():
                        ts = row["timestamp"]
                        if hasattr(ts, "isoformat"):
                            ts_str = ts.isoformat()
                        else:
                            ts_str = str(ts)
                        if cutoff_time:
                            try:
                                ts_dt = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00")
                                )
                                if ts_dt < cutoff_time:
                                    continue
                            except Exception:
                                pass
                        history.append(
                            {"timestamp": ts_str, "value": float(row["market_value"])}
                        )
            except Exception:
                continue
    except ImportError:
        pass

    # Read from JSONL files (recent data)
    jsonl_files = sorted(port_dir.glob("*.jsonl"))
    for jf in jsonl_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = data.get("timestamp")
                        mv = data.get("market_value")
                        if ts and mv is not None:
                            if cutoff_time:
                                try:
                                    ts_str = ts if isinstance(ts, str) else str(ts)
                                    ts_dt = datetime.fromisoformat(
                                        ts_str.replace("Z", "+00:00")
                                    )
                                    if ts_dt < cutoff_time:
                                        continue
                                except Exception:
                                    pass
                            # Handle market_value that might be a dict
                            if isinstance(mv, dict):
                                mv = mv.get("__root__", mv)
                            history.append(
                                {
                                    "timestamp": ts if isinstance(ts, str) else str(ts),
                                    "value": float(mv),
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            continue

    # Sort by timestamp
    history.sort(key=lambda x: x.get("timestamp", ""))

    # Apply limit if specified
    if limit and len(history) > limit:
        # Downsample to fit limit while preserving time range
        step = len(history) // limit
        if step > 1:
            history = history[::step][:limit]
        else:
            history = history[-limit:]

    return history
