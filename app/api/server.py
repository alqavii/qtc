from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional, List
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from app.config.environments import config
from app.services.auth import auth_manager
from app.telemetry import get_recent_activity_entries, subscribe_activity

import json


app = FastAPI(title="QTC Alpha API", version="1.0")

# Enable simple, safe CORS so the frontend can fetch from browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"]
)


def _tail_jsonl(path: Path) -> Optional[Dict[str, Any]]:
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


def _list_team_ids() -> List[str]:
    root = config.get_data_path("team")
    if not root.exists():
        return []
    return [p.name for p in root.iterdir() if p.is_dir()]


def _team_status_dict(team_id: str) -> Dict[str, Any]:
    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"
    latest_json = None
    if port_dir.exists():
        files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
        if files:
            latest_json = files[-1]
    snapshot = _tail_jsonl(latest_json) if latest_json else None
    metrics = _tail_jsonl(team_dir / "metrics.jsonl")
    return {"team_id": team_id, "snapshot": snapshot, "metrics": metrics}


def _calculate_performance_metrics(history: List[Dict[str, Any]], initial_value: Optional[float] = None) -> Dict[str, Any]:
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
            "data_points": len(history)
        }
    
    try:
        import numpy as np
        from datetime import datetime
        
        # Extract values and timestamps
        values = np.array([float(h['value']) for h in history])
        timestamps = [datetime.fromisoformat(h['timestamp'].replace('Z', '+00:00')) for h in history]
        
        # Handle edge case: all zero values
        if np.all(values == 0):
            return {
                "error": "All portfolio values are zero",
                "data_points": len(history)
            }
        
        # Calculate returns, handling division by zero
        with np.errstate(divide='ignore', invalid='ignore'):
            returns = np.diff(values) / values[:-1]
        
        # Filter out invalid returns (inf, -inf, nan)
        valid_returns = returns[np.isfinite(returns)]
        
        if len(valid_returns) < 2:
            return {
                "error": "Insufficient valid returns for metrics calculation",
                "data_points": len(history),
                "valid_returns": len(valid_returns)
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
            annualized_return = mean_return * periods_per_year if years_elapsed > 0 else 0
            annualized_volatility = 0.0
            sharpe_ratio = 0.0 if abs(annualized_return) < 1e-10 else (np.inf if annualized_return > 0 else -np.inf)
            sortino_ratio = 0.0
        else:
            # Normal calculations
            annualized_return = mean_return * periods_per_year if years_elapsed > 0 else 0
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
        with np.errstate(divide='ignore', invalid='ignore'):
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
        
        total_return_percentage = total_return * 100 if np.isfinite(total_return) else total_return
        
        # Win rate
        win_rate = float(np.sum(returns > 0) / len(returns)) if len(returns) > 0 else 0
        
        # Average win/loss
        winning_returns = returns[returns > 0]
        losing_returns = returns[returns < 0]
        avg_win = float(np.mean(winning_returns)) if len(winning_returns) > 0 else 0
        avg_loss = float(np.mean(losing_returns)) if len(losing_returns) > 0 else 0
        
        # Profit factor
        total_wins = float(np.sum(winning_returns)) if len(winning_returns) > 0 else 0
        total_losses = abs(float(np.sum(losing_returns))) if len(losing_returns) > 0 else 0
        
        if total_losses < 1e-10:
            # No losses
            if total_wins > 1e-10:
                profit_factor = np.inf  # All wins, no losses
            else:
                profit_factor = 0.0  # No wins, no losses
        else:
            profit_factor = total_wins / total_losses
        
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
            "win_rate": safe_float(win_rate),
            "win_rate_percentage": safe_float(win_rate * 100),
            "profit_factor": safe_float(profit_factor),
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
                "drawdown_amount": safe_float(max_dd_peak - max_dd_value)
            },
            "period": {
                "start": timestamps[0].isoformat(),
                "end": timestamps[-1].isoformat(),
                "days": float(days_elapsed),
                "data_points": len(history)
            }
        }
        
    except Exception as e:
        return {
            "error": f"Metrics calculation failed: {str(e)}",
            "data_points": len(history)
        }


def _read_portfolio_history(
    team_id: str, 
    days: Optional[int] = None, 
    limit: Optional[int] = None
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
    
    # 1. Read from parquet file (historical consolidated data)
    pq_path = port_dir / "portfolio.parquet"
    if pq_path.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(pq_path)
            
            # Apply time filter
            if cutoff_time is not None and 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                df = df[df['timestamp'] >= cutoff_time]
            
            # Extract relevant fields
            for _, row in df.iterrows():
                try:
                    timestamp = row.get('timestamp')
                    if isinstance(timestamp, pd.Timestamp):
                        timestamp = timestamp.isoformat()
                    elif isinstance(timestamp, datetime):
                        timestamp = timestamp.isoformat()
                    
                    market_value = row.get('market_value')
                    if market_value is not None:
                        history.append({
                            "timestamp": timestamp,
                            "value": float(market_value)
                        })
                except Exception:
                    continue
        except Exception:
            pass
    
    # 2. Read from JSONL files (recent data, not yet folded into parquet)
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])
    
    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        timestamp_str = data.get('timestamp')
                        
                        # Parse timestamp
                        if timestamp_str:
                            try:
                                ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                            except Exception:
                                continue
                            
                            # Apply time filter
                            if cutoff_time is not None and ts < cutoff_time:
                                continue
                        
                        # Extract market value
                        market_value = data.get('market_value')
                        if market_value is not None:
                            # Handle nested __root__ structure if present
                            if isinstance(market_value, dict):
                                market_value = market_value.get('__root__', market_value)
                            
                            history.append({
                                "timestamp": timestamp_str,
                                "value": float(market_value)
                            })
                    except Exception:
                        continue
        except Exception:
            continue
    
    # Sort by timestamp
    history.sort(key=lambda x: x['timestamp'])
    
    # Apply limit if specified
    if limit is not None and len(history) > limit:
        # Take evenly spaced samples to maintain shape
        step = len(history) // limit
        if step > 1:
            history = history[::step][:limit]
        else:
            history = history[-limit:]
    
    return history


@app.get("/leaderboard")
def get_leaderboard():
    out: List[Dict[str, Any]] = []
    for tid in _list_team_ids():
        team_dir = config.get_data_path(f"team/{tid}")
        port_dir = team_dir / "portfolio"
        latest_json = None
        if port_dir.exists():
            files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
            if files:
                latest_json = files[-1]
        snap = _tail_jsonl(latest_json) if latest_json else None
        value = None
        if isinstance(snap, dict):
            raw_value = snap.get('market_value')
            if isinstance(raw_value, dict):
                raw_value = raw_value.get('__root__', raw_value)
            try:
                value = float(raw_value) if raw_value is not None else None
            except Exception:
                value = None
        out.append({'team_id': tid, 'portfolio_value': value})
    # Sort by portfolio value desc if present
    out.sort(
        key=lambda r: (
            float(r["portfolio_value"]) if r["portfolio_value"] is not None else -1e18
        ),
        reverse=True,
    )
    return {"leaderboard": out}


def _team_line(team_id: str) -> str:
    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"
    latest_json = None
    if port_dir.exists():
        files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
        if files:
            latest_json = files[-1]
    snapshot = _tail_jsonl(latest_json) if latest_json else None
    if not isinstance(snapshot, dict):
        return f"{team_id} | No data"

    cash = snapshot.get("cash")
    mv = snapshot.get("market_value")
    positions = snapshot.get("positions") or {}

    def _fmt_money(x: Any) -> str:
        try:
            return f"${float(x):,.2f}"
        except Exception:
            return str(x)

    pos_list: List[str] = []
    for sym, p in positions.items():
        qty = p.get("quantity", 0)
        value = p.get("value")
        price = None
        try:
            qf = float(qty)
            if qf:
                price = (
                    (float(value) / qf)
                    if value is not None
                    else float(p.get("avg_cost", 0))
                )
            else:
                price = float(p.get("avg_cost", 0))
        except Exception:
            price = p.get("avg_cost")
        pos_list.append(f'["{sym}", {_fmt_money(price)}, {qty}]')

    pos_str = ", ".join(pos_list)
    return f"{team_id} | Cash: {_fmt_money(cash)} | Portfolio Value: {_fmt_money(mv)} | Positions: [{pos_str}]"


@app.get("/activity/recent")
def get_activity_recent(limit: int = 100):
    limit = max(1, min(limit, 500))
    return {"activity": get_recent_activity_entries(limit)}


@app.get("/activity/stream")
async def stream_activity(request: Request):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()
    stop_event = threading.Event()

    def pump() -> None:
        try:
            for entry in subscribe_activity(tail=200, stop_event=stop_event):
                payload = f"{entry.timestamp.isoformat()} | {entry.message}"
                loop.call_soon_threadsafe(queue.put_nowait, payload)
                if stop_event.is_set():
                    break
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    break
                yield f"data: {item}\n\n"
        finally:
            stop_event.set()
            thread.join(timeout=1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get('/line/{team_key}')
def get_team_status_by_team_key(team_key: str):
    """Lookup team by API key and return JSON status (team_id, snapshot, metrics)."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        raise HTTPException(status_code=401, detail='invalid key')
    return _team_status_dict(team_id)


@app.get("/api/v1/team/{team_id}/history")
def get_team_history(
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(7, description="Number of days to look back", ge=1, le=365),
    limit: Optional[int] = Query(1000, description="Maximum number of data points", ge=1, le=10000)
):
    """Get historical portfolio values for a specific team.
    
    This endpoint returns time-series data of portfolio values for visualization.
    Combines data from both historical parquet files and recent JSONL snapshots.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier (e.g., 'test1', 'team-alpha')
    - `key`: Team API key for authentication
    - `days`: Number of days to look back (default: 7, max: 365)
    - `limit`: Maximum number of data points to return (default: 1000, max: 10000)
    
    **Returns:**
    ```json
    {
        "team_id": "test1",
        "days": 7,
        "data_points": 1000,
        "history": [
            {"timestamp": "2025-10-10T14:30:00+00:00", "value": 10500.25},
            {"timestamp": "2025-10-10T14:31:00+00:00", "value": 10502.50}
        ]
    }
    ```
    
    **Use Cases:**
    - Line charts showing portfolio value over time
    - Performance tracking and analysis
    - Calculating returns and drawdowns
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    history = _read_portfolio_history(team_id, days=days, limit=limit)
    
    return {
        "team_id": team_id,
        "days": days,
        "data_points": len(history),
        "history": history
    }


@app.get("/api/v1/leaderboard/history")
def get_leaderboard_history(
    days: Optional[int] = Query(7, description="Number of days to look back", ge=1, le=365),
    limit: Optional[int] = Query(500, description="Max data points per team", ge=1, le=5000)
):
    """Get historical portfolio values for all teams (public endpoint).
    
    This endpoint returns time-series data for all teams, useful for creating
    comparative visualizations like racing bar charts or multi-line graphs.
    
    **Authentication:** None required (public endpoint)
    
    **Parameters:**
    - `days`: Number of days to look back (default: 7, max: 365)
    - `limit`: Maximum number of data points per team (default: 500, max: 5000)
    
    **Returns:**
    ```json
    {
        "days": 7,
        "teams": {
            "test1": [
                {"timestamp": "2025-10-10T14:30:00+00:00", "value": 10500.25},
                {"timestamp": "2025-10-10T14:31:00+00:00", "value": 10502.50}
            ],
            "test2": [
                {"timestamp": "2025-10-10T14:30:00+00:00", "value": 9800.00},
                {"timestamp": "2025-10-10T14:31:00+00:00", "value": 9805.75}
            ]
        }
    }
    ```
    
    **Use Cases:**
    - Multi-team comparison charts
    - Racing bar charts
    - Leaderboard with historical context
    """
    all_teams_history: Dict[str, List[Dict[str, Any]]] = {}
    
    for team_id in _list_team_ids():
        history = _read_portfolio_history(team_id, days=days, limit=limit)
        if history:  # Only include teams with data
            all_teams_history[team_id] = history
    
    return {
        "days": days,
        "teams": all_teams_history
    }


@app.get("/api/v1/team/{team_id}/trades")
def get_team_trades(
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    limit: Optional[int] = Query(100, description="Maximum number of trades", ge=1, le=1000)
):
    """Get recent trade history for a specific team.
    
    Returns a list of executed trades with details about each transaction.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key for authentication
    - `limit`: Maximum number of trades to return (default: 100, max: 1000)
    
    **Returns:**
    ```json
    {
        "team_id": "test1",
        "trades": [
            {
                "timestamp": "2025-10-10T14:30:00+00:00",
                "symbol": "NVDA",
                "side": "buy",
                "quantity": 10,
                "price": 500.25,
                "value": 5002.50
            }
        ]
    }
    ```
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    team_dir = config.get_data_path(f"team/{team_id}")
    trades_file = team_dir / "trades.jsonl"
    
    trades: List[Dict[str, Any]] = []
    
    if trades_file.exists():
        try:
            # Read trades from file (most recent first)
            with open(trades_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Take last N lines
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                    trades.append(trade)
                except Exception:
                    continue
        except Exception:
            pass
    
    # Reverse to show most recent first
    trades.reverse()
    
    return {
        "team_id": team_id,
        "count": len(trades),
        "trades": trades
    }


@app.get("/api/v1/team/{team_id}/metrics")
def get_team_metrics(
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(None, description="Days to calculate metrics over (None = all data)", ge=1, le=365)
):
    """Get performance metrics for a specific team.
    
    Calculate comprehensive performance metrics including Sharpe ratio, Sortino ratio,
    Calmar ratio, maximum drawdown, total return, and more.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key for authentication
    - `days`: Number of days to calculate metrics over (default: all available data)
    
    **Returns:**
    ```json
    {
        "team_id": "test1",
        "metrics": {
            "sharpe_ratio": 1.85,
            "sortino_ratio": 2.34,
            "calmar_ratio": 3.21,
            "max_drawdown": -0.0542,
            "max_drawdown_percentage": -5.42,
            "current_drawdown": -0.0023,
            "current_drawdown_percentage": -0.23,
            "total_return": 0.0542,
            "total_return_percentage": 5.42,
            "annualized_return": 0.1247,
            "annualized_return_percentage": 12.47,
            "annualized_volatility": 0.0673,
            "annualized_volatility_percentage": 6.73,
            "win_rate": 0.58,
            "win_rate_percentage": 58.0,
            "profit_factor": 1.45,
            "avg_win": 0.0012,
            "avg_loss": -0.0009,
            "total_trades": 250,
            "winning_trades": 145,
            "losing_trades": 105,
            "current_value": 10542.75,
            "starting_value": 10000.00,
            "peak_value": 10650.25,
            "trough_value": 9875.50,
            "max_drawdown_details": {
                "peak_value": 10650.25,
                "trough_value": 10075.30,
                "drawdown_amount": 574.95
            },
            "period": {
                "start": "2025-10-03T09:30:00+00:00",
                "end": "2025-10-10T16:00:00+00:00",
                "days": 7.27,
                "data_points": 2835
            }
        }
    }
    ```
    
    **Metrics Explained:**
    - **Sharpe Ratio**: Risk-adjusted return (higher is better, >1 is good, >2 is excellent)
    - **Sortino Ratio**: Similar to Sharpe but only considers downside volatility
    - **Calmar Ratio**: Return relative to maximum drawdown (higher is better)
    - **Max Drawdown**: Largest peak-to-trough decline (negative percentage)
    - **Total Return**: Overall return since start (percentage)
    - **Win Rate**: Percentage of profitable periods
    - **Profit Factor**: Ratio of total wins to total losses (>1 is profitable)
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    # Get portfolio history
    history = _read_portfolio_history(team_id, days=days, limit=None)
    
    if not history:
        raise HTTPException(status_code=404, detail='No historical data available for this team')
    
    # Calculate metrics
    metrics = _calculate_performance_metrics(history)
    
    return {
        "team_id": team_id,
        "metrics": metrics
    }


@app.get("/api/v1/leaderboard/metrics")
def get_leaderboard_with_metrics(
    days: Optional[int] = Query(None, description="Days to calculate metrics over (None = all)", ge=1, le=365),
    sort_by: str = Query("portfolio_value", description="Sort by: portfolio_value, sharpe_ratio, total_return, calmar_ratio")
):
    """Get leaderboard with comprehensive performance metrics for all teams.
    
    Returns current portfolio values and performance metrics including Sharpe, Sortino,
    Calmar ratios, drawdowns, and returns for all teams.
    
    **Authentication:** None required (public endpoint)
    
    **Parameters:**
    - `days`: Number of days to calculate metrics over (default: all available data)
    - `sort_by`: Sort criterion - one of: portfolio_value, sharpe_ratio, total_return, calmar_ratio, sortino_ratio
    
    **Returns:**
    ```json
    {
        "leaderboard": [
            {
                "team_id": "test1",
                "rank": 1,
                "portfolio_value": 10542.75,
                "sharpe_ratio": 1.85,
                "sortino_ratio": 2.34,
                "calmar_ratio": 3.21,
                "max_drawdown_percentage": -5.42,
                "total_return_percentage": 5.42,
                "annualized_return_percentage": 12.47,
                "win_rate_percentage": 58.0,
                "profit_factor": 1.45
            }
        ],
        "sort_by": "portfolio_value",
        "calculation_period_days": 7
    }
    ```
    
    **Use Cases:**
    - Display comprehensive leaderboard with all metrics
    - Sort by different performance criteria
    - Compare teams across multiple dimensions
    """
    valid_sort_keys = ["portfolio_value", "sharpe_ratio", "total_return", "calmar_ratio", 
                       "sortino_ratio", "total_return_percentage", "annualized_return"]
    
    if sort_by not in valid_sort_keys:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid sort_by value. Must be one of: {', '.join(valid_sort_keys)}"
        )
    
    leaderboard: List[Dict[str, Any]] = []
    
    for team_id in _list_team_ids():
        # Get current portfolio value
        team_dir = config.get_data_path(f"team/{team_id}")
        port_dir = team_dir / "portfolio"
        latest_json = None
        if port_dir.exists():
            files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
            if files:
                latest_json = files[-1]
        
        snap = _tail_jsonl(latest_json) if latest_json else None
        portfolio_value = None
        if isinstance(snap, dict):
            raw_value = snap.get('market_value')
            if isinstance(raw_value, dict):
                raw_value = raw_value.get('__root__', raw_value)
            try:
                portfolio_value = float(raw_value) if raw_value is not None else None
            except Exception:
                portfolio_value = None
        
        # Get metrics
        history = _read_portfolio_history(team_id, days=days, limit=None)
        
        if history:
            metrics = _calculate_performance_metrics(history)
            
            # Extract key metrics (handle potential errors)
            if "error" not in metrics:
                team_data = {
                    "team_id": team_id,
                    "portfolio_value": portfolio_value,
                    "sharpe_ratio": metrics.get("sharpe_ratio"),
                    "sortino_ratio": metrics.get("sortino_ratio"),
                    "calmar_ratio": metrics.get("calmar_ratio"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "max_drawdown_percentage": metrics.get("max_drawdown_percentage"),
                    "current_drawdown_percentage": metrics.get("current_drawdown_percentage"),
                    "total_return": metrics.get("total_return"),
                    "total_return_percentage": metrics.get("total_return_percentage"),
                    "annualized_return": metrics.get("annualized_return"),
                    "annualized_return_percentage": metrics.get("annualized_return_percentage"),
                    "annualized_volatility_percentage": metrics.get("annualized_volatility_percentage"),
                    "win_rate_percentage": metrics.get("win_rate_percentage"),
                    "profit_factor": metrics.get("profit_factor"),
                    "total_trades": metrics.get("total_trades"),
                    "current_value": metrics.get("current_value"),
                    "starting_value": metrics.get("starting_value"),
                }
            else:
                # Metrics calculation failed, include basic info only
                team_data = {
                    "team_id": team_id,
                    "portfolio_value": portfolio_value,
                    "sharpe_ratio": None,
                    "sortino_ratio": None,
                    "calmar_ratio": None,
                    "metrics_error": metrics.get("error")
                }
        else:
            # No historical data
            team_data = {
                "team_id": team_id,
                "portfolio_value": portfolio_value,
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "calmar_ratio": None,
                "metrics_error": "No historical data available"
            }
        
        leaderboard.append(team_data)
    
    # Sort by requested criterion
    def sort_key(team: Dict[str, Any]) -> float:
        value = team.get(sort_by)
        if value is None:
            return -1e18  # Put None values at the bottom
        return float(value)
    
    leaderboard.sort(key=sort_key, reverse=True)
    
    # Add rank
    for idx, team in enumerate(leaderboard, start=1):
        team["rank"] = idx
    
    return {
        "leaderboard": leaderboard,
        "sort_by": sort_by,
        "calculation_period_days": days if days else "all"
    }


@app.get('/{team_key}', response_class=PlainTextResponse)
def get_team_line_by_team_key(team_key: str):
    """Lookup team by API key and return a single-line status for CLI display."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        raise HTTPException(status_code=401, detail='invalid key')
    return _team_line(team_id)
