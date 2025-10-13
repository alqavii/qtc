from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request, Query, File, UploadFile, Form
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from typing import Dict, Any, Optional, List
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from app.config.environments import config
from app.services.auth import auth_manager
from app.telemetry import get_recent_activity_entries, subscribe_activity
from app.telemetry.error_handler import error_handler_instance
import shutil
import tempfile
import zipfile

import json
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


app = FastAPI(title="QTC Alpha API", version="1.0")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request body size limits.
    
    Prevents memory exhaustion from large uploads by checking Content-Length
    header before reading the request body. Returns 413 Payload Too Large
    for oversized requests.
    """
    
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB for single files
    MAX_PACKAGE_SIZE = 50 * 1024 * 1024  # 50MB for ZIP packages
    
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and "upload" in request.url.path:
            content_length = request.headers.get("content-length")
            
            if content_length:
                content_length = int(content_length)
                
                if "upload-strategy-package" in request.url.path:
                    max_size = self.MAX_PACKAGE_SIZE
                    max_size_mb = 50
                else:
                    max_size = self.MAX_UPLOAD_SIZE
                    max_size_mb = 10
                
                if content_length > max_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": f"Request body too large. Maximum allowed size is {max_size_mb}MB",
                            "status_code": 413,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "path": str(request.url.path),
                            "received_size_mb": round(content_length / (1024 * 1024), 2),
                            "max_size_mb": max_size_mb
                        }
                    )
        
        response = await call_next(request)
        return response


app.add_middleware(RequestSizeLimitMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPException errors with consistent JSON responses.
    
    Catches all HTTPException errors (401, 404, 400, etc.) and returns
    a standardized JSON response. Logs all errors to telemetry without
    exposing stack traces to clients.
    """
    error_handler_instance.handle_system_error(
        exc,
        component=f"api:{request.url.path}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": str(request.url.path)
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with detailed error messages.
    
    Catches FastAPI validation errors (invalid query params, missing fields,
    type mismatches) and returns a 422 response with specific field-level
    error details to help clients fix their requests.
    """
    error_handler_instance.handle_system_error(
        exc,
        component=f"api:{request.url.path}"
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "status_code": 422,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": str(request.url.path),
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions with safe error responses.
    
    Catches any unhandled exceptions (KeyError, ValueError, etc.) and returns
    a generic 500 error without exposing internal implementation details or
    stack traces. Full exception details are logged to telemetry for debugging.
    """
    error_handler_instance.handle_system_error(
        exc,
        component=f"api:{request.url.path}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": str(request.url.path)
        }
    )


# Enable simple, safe CORS so the frontend can fetch from browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
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
@limiter.limit("100/minute")
def get_leaderboard(request: Request):
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
@limiter.limit("100/minute")
def get_activity_recent(request: Request, limit: int = 100):
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
@limiter.limit("200/minute")
def get_team_status_by_team_key(request: Request, team_key: str):
    """Lookup team by API key and return JSON status (team_id, snapshot, metrics)."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        raise HTTPException(status_code=401, detail='invalid key')
    return _team_status_dict(team_id)


@app.get("/api/v1/team/{team_id}/history")
@limiter.limit("200/minute")
def get_team_history(
    request: Request,
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
@limiter.limit("100/minute")
def get_leaderboard_history(
    request: Request,
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
@limiter.limit("100/minute")
def get_leaderboard_with_metrics(
    request: Request,
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


# ============================================================================
# STRATEGY UPLOAD ENDPOINTS
# ============================================================================

def _validate_strategy_files(directory: Path) -> Dict[str, Any]:
    """Validate all Python files in a directory for security.
    
    Returns:
        Dictionary with validation results including file list and any errors
    """
    from app.loaders.static_check import ast_sanity_check
    
    # Check that strategy.py exists
    strategy_file = directory / "strategy.py"
    if not strategy_file.exists():
        return {
            "valid": False,
            "error": "strategy.py not found in upload. This file is required as the entry point.",
            "files": []
        }
    
    # Get list of all Python files
    py_files = list(directory.rglob("*.py"))
    file_list = [str(f.relative_to(directory)) for f in py_files]
    
    # Run security validation on all files
    try:
        ast_sanity_check(directory)  # Validates all .py files recursively
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "files": file_list
        }
    
    return {
        "valid": True,
        "files": file_list,
        "file_count": len(file_list)
    }


def _update_team_registry(team_id: str, repo_dir: Path) -> None:
    """Update team registry to use the uploaded strategy directory."""
    import yaml
    
    registry_path = Path("/opt/qtc/team_registry.yaml")
    
    # Load registry
    if registry_path.exists():
        reg = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    else:
        reg = {}
    
    teams = reg.setdefault("teams", [])
    
    # Update or create team entry
    found = False
    for team in teams:
        if team.get("team_id") == team_id:
            team["repo_dir"] = str(repo_dir)
            team.pop("git_url", None)  # Remove git_url if present
            found = True
            break
    
    if not found:
        # Team doesn't exist in registry, create basic entry
        teams.append({
            "team_id": team_id,
            "repo_dir": str(repo_dir),
            "entry_point": "strategy:Strategy",
            "initial_cash": 100000,
            "run_24_7": False
        })
    
    # Save registry
    registry_path.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")


@app.post("/api/v1/team/{team_id}/upload-strategy")
@limiter.limit("20/hour")
async def upload_single_strategy(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    strategy_file: UploadFile = File(..., description="strategy.py file")
):
    """Upload a single strategy.py file for a team.
    
    This endpoint is for simple, single-file strategies. For multi-file strategies,
    use the /upload-strategy-package endpoint with a ZIP file.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key (form field)
    - `strategy_file`: Python file to upload (must be named strategy.py)
    
    **Example using curl:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/team/test1/upload-strategy" \
      -F "key=YOUR_API_KEY" \
      -F "strategy_file=@strategy.py"
    ```
    
    **Returns:**
    ```json
    {
        "success": true,
        "message": "Strategy uploaded successfully",
        "team_id": "test1",
        "files_uploaded": ["strategy.py"],
        "path": "/opt/qtc/external_strategies/test1",
        "note": "Strategy will be loaded on the next trading cycle"
    }
    ```
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    # Validate filename
    if not strategy_file.filename.endswith('.py'):
        raise HTTPException(status_code=400, detail='File must be a Python (.py) file')
    
    # Read file content
    try:
        content = await strategy_file.read()
        
        # Validate file size (10MB limit)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f'File too large: {len(content) / (1024 * 1024):.2f}MB. Maximum size is 10MB'
            )
        
        code_str = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail='File must be valid UTF-8 encoded text')
    
    # Validate in temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        temp_strategy = temp_path / "strategy.py"
        temp_strategy.write_text(code_str, encoding='utf-8')
        
        # Security validation
        validation = _validate_strategy_files(temp_path)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=f'Validation failed: {validation["error"]}')
    
    # If validation passed, save to external_strategies
    strategy_dir = Path("/opt/qtc/external_strategies") / team_id
    strategy_dir.mkdir(parents=True, exist_ok=True)
    
    strategy_path = strategy_dir / "strategy.py"
    strategy_path.write_text(code_str, encoding='utf-8')
    
    # Update registry
    _update_team_registry(team_id, strategy_dir)
    
    return {
        "success": True,
        "message": f"Strategy uploaded successfully for {team_id}",
        "team_id": team_id,
        "files_uploaded": ["strategy.py"],
        "path": str(strategy_dir),
        "note": "Strategy will be loaded on the next trading cycle"
    }


@app.post("/api/v1/team/{team_id}/upload-strategy-package")
@limiter.limit("20/hour")
async def upload_strategy_package(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    strategy_zip: UploadFile = File(..., description="ZIP file containing strategy.py and helper modules")
):
    """Upload a ZIP package containing strategy.py and multiple helper files.
    
    This endpoint supports complex, multi-file strategies. The ZIP should contain:
    - strategy.py (required) - Main entry point with Strategy class
    - Any number of additional .py files (helpers, utilities, etc.)
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key (form field)
    - `strategy_zip`: ZIP file containing Python files
    
    **ZIP Structure Example:**
    ```
    strategy_package.zip
    ├── strategy.py          # Required entry point
    ├── indicators.py        # Helper module
    ├── risk_manager.py      # Helper module
    └── utils.py             # Helper module
    ```
    
    **Example using curl:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/team/test1/upload-strategy-package" \
      -F "key=YOUR_API_KEY" \
      -F "strategy_zip=@my_strategy.zip"
    ```
    
    **Example using Python requests:**
    ```python
    import requests
    
    files = {'strategy_zip': open('strategy_package.zip', 'rb')}
    data = {'key': 'YOUR_API_KEY'}
    response = requests.post(
        'http://localhost:8000/api/v1/team/test1/upload-strategy-package',
        files=files,
        data=data
    )
    print(response.json())
    ```
    
    **Returns:**
    ```json
    {
        "success": true,
        "message": "Strategy package uploaded successfully",
        "team_id": "test1",
        "files_uploaded": [
            "strategy.py",
            "indicators.py",
            "risk_manager.py",
            "utils.py"
        ],
        "file_count": 4,
        "path": "/opt/qtc/external_strategies/test1",
        "validation": {
            "all_files_validated": true,
            "security_checks_passed": true
        }
    }
    ```
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    # Validate file type
    if not strategy_zip.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail='File must be a ZIP archive')
    
    # Read ZIP content
    content = await strategy_zip.read()
    
    # Validate file size (50MB limit for ZIP packages)
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f'ZIP file too large: {len(content) / (1024 * 1024):.2f}MB. Maximum size is 50MB'
        )
    
    # Extract and validate in temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "upload.zip"
        zip_path.write_bytes(content)
        
        try:
            # Extract ZIP with security checks
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Security: Check for path traversal attempts
                for member in zip_ref.namelist():
                    # Normalize the path
                    member_path = Path(member).resolve()
                    
                    # Check for absolute paths or parent directory references
                    if member.startswith('/') or '..' in Path(member).parts:
                        raise HTTPException(
                            status_code=400,
                            detail=f'Invalid file path in ZIP: {member}. Paths must be relative and not use ..'
                        )
                    
                    # Check file size (prevent zip bombs)
                    info = zip_ref.getinfo(member)
                    if info.file_size > 10 * 1024 * 1024:  # 10 MB limit per file
                        raise HTTPException(
                            status_code=400,
                            detail=f'File {member} is too large (max 10 MB per file)'
                        )
                
                # Extract to temporary location
                extracted_dir = temp_path / "extracted"
                zip_ref.extractall(extracted_dir)
        
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail='Invalid or corrupted ZIP file')
        
        # Validate extracted files
        validation = _validate_strategy_files(extracted_dir)
        
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f'Strategy validation failed: {validation["error"]}'
            )
        
        # If validation passed, copy to external_strategies
        strategy_dir = Path("/opt/qtc/external_strategies") / team_id
        
        # Remove old strategy files
        if strategy_dir.exists():
            shutil.rmtree(strategy_dir)
        
        # Copy validated files
        shutil.copytree(extracted_dir, strategy_dir)
    
    # Update registry
    _update_team_registry(team_id, strategy_dir)
    
    return {
        "success": True,
        "message": f"Strategy package uploaded successfully for {team_id}",
        "team_id": team_id,
        "files_uploaded": validation["files"],
        "file_count": validation["file_count"],
        "path": str(strategy_dir),
        "validation": {
            "all_files_validated": True,
            "security_checks_passed": True
        },
        "note": "Strategy will be loaded on the next trading cycle"
    }


@app.post("/api/v1/team/{team_id}/upload-multiple-files")
@limiter.limit("20/hour")
async def upload_multiple_files(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    files: List[UploadFile] = File(..., description="Multiple Python files (must include strategy.py)")
):
    """Upload multiple Python files for a multi-file strategy.
    
    Alternative to ZIP upload - allows uploading multiple individual files.
    One of the files must be named strategy.py (the entry point).
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key (form field)
    - `files`: Multiple Python files (must include strategy.py)
    
    **Example using curl:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/team/test1/upload-multiple-files" \
      -F "key=YOUR_API_KEY" \
      -F "files=@strategy.py" \
      -F "files=@indicators.py" \
      -F "files=@utils.py"
    ```
    
    **Example using Python requests:**
    ```python
    import requests
    
    files_to_upload = [
        ('files', open('strategy.py', 'rb')),
        ('files', open('indicators.py', 'rb')),
        ('files', open('utils.py', 'rb'))
    ]
    data = {'key': 'YOUR_API_KEY'}
    response = requests.post(
        'http://localhost:8000/api/v1/team/test1/upload-multiple-files',
        files=files_to_upload,
        data=data
    )
    print(response.json())
    ```
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    # Check that at least one file is provided
    if not files:
        raise HTTPException(status_code=400, detail='No files provided')
    
    # Validate and save to temporary directory first
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        uploaded_files = []
        total_size = 0
        
        for file in files:
            # Validate file extension
            if not file.filename.endswith('.py'):
                raise HTTPException(
                    status_code=400,
                    detail=f'All files must be Python (.py) files. Invalid: {file.filename}'
                )
            
            # Validate filename (no path traversal)
            filename = Path(file.filename).name
            if filename != file.filename or '..' in filename:
                raise HTTPException(
                    status_code=400,
                    detail=f'Invalid filename: {file.filename}'
                )
            
            # Read and save file
            try:
                content = await file.read()
                
                # Track total size (limit to 50MB total)
                total_size += len(content)
                if total_size > 50 * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail=f'Total upload size too large: {total_size / (1024 * 1024):.2f}MB. Maximum is 50MB'
                    )
                
                code_str = content.decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail=f'File {file.filename} must be valid UTF-8 encoded text'
                )
            
            file_path = temp_path / filename
            file_path.write_text(code_str, encoding='utf-8')
            uploaded_files.append(filename)
        
        # Validate all files
        validation = _validate_strategy_files(temp_path)
        
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f'Strategy validation failed: {validation["error"]}'
            )
        
        # If validation passed, copy to external_strategies
        strategy_dir = Path("/opt/qtc/external_strategies") / team_id
        
        # Remove old strategy files
        if strategy_dir.exists():
            shutil.rmtree(strategy_dir)
        
        # Copy validated files
        shutil.copytree(temp_path, strategy_dir)
    
    # Update registry
    _update_team_registry(team_id, strategy_dir)
    
    return {
        "success": True,
        "message": f"Multiple files uploaded successfully for {team_id}",
        "team_id": team_id,
        "files_uploaded": uploaded_files,
        "file_count": len(uploaded_files),
        "path": str(strategy_dir),
        "validation": {
            "all_files_validated": True,
            "security_checks_passed": True
        },
        "note": "Strategy will be loaded on the next trading cycle"
    }
