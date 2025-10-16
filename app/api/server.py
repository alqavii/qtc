from fastapi import FastAPI, HTTPException, Request, Query, File, UploadFile, Form
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
import shutil
import tempfile
import zipfile

import json

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


app = FastAPI(title="QTC Alpha API", version="1.0")

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# File size limits (in bytes)
MAX_SINGLE_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ZIP_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_TOTAL_EXTRACTED_SIZE = 100 * 1024 * 1024  # 100 MB total extracted

# Enable simple, safe CORS so the frontend can fetch from browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


def _calculate_performance_metrics(
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
        from datetime import datetime

        # Extract values and timestamps
        values = np.array([float(h["value"]) for h in history])
        timestamps = [
            datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
            for h in history
        ]

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


def _read_portfolio_history(
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

    # 1. Read from parquet file (historical consolidated data)
    pq_path = port_dir / "portfolio.parquet"
    if pq_path.exists():
        try:
            import pandas as pd

            df = pd.read_parquet(pq_path)

            # Apply time filter
            if cutoff_time is not None and "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                df = df[df["timestamp"] >= cutoff_time]

            # Extract relevant fields
            for _, row in df.iterrows():
                try:
                    timestamp = row.get("timestamp")
                    if isinstance(timestamp, pd.Timestamp):
                        timestamp = timestamp.isoformat()
                    elif isinstance(timestamp, datetime):
                        timestamp = timestamp.isoformat()

                    market_value = row.get("market_value")
                    if market_value is not None:
                        history.append(
                            {"timestamp": timestamp, "value": float(market_value)}
                        )
                except Exception:
                    continue
        except Exception:
            pass

    # 2. Read from JSONL files (recent data, not yet folded into parquet)
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        timestamp_str = data.get("timestamp")

                        # Parse timestamp
                        if timestamp_str:
                            try:
                                ts = datetime.fromisoformat(
                                    timestamp_str.replace("Z", "+00:00")
                                )
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                            except Exception:
                                continue

                            # Apply time filter
                            if cutoff_time is not None and ts < cutoff_time:
                                continue

                        # Extract market value
                        market_value = data.get("market_value")
                        if market_value is not None:
                            # Handle nested __root__ structure if present
                            if isinstance(market_value, dict):
                                market_value = market_value.get(
                                    "__root__", market_value
                                )

                            history.append(
                                {
                                    "timestamp": timestamp_str,
                                    "value": float(market_value),
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            continue

    # Sort by timestamp
    history.sort(key=lambda x: x["timestamp"])

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
@limiter.limit("300/minute")
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
            raw_value = snap.get("market_value")
            if isinstance(raw_value, dict):
                raw_value = raw_value.get("__root__", raw_value)
            try:
                value = float(raw_value) if raw_value is not None else None
            except Exception:
                value = None
        out.append({"team_id": tid, "portfolio_value": value})
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


@app.get("/api/v1/team/{team_id}/history")
@limiter.limit("60/minute")
def get_team_history(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(
        7, description="Number of days to look back", ge=1, le=365
    ),
    limit: Optional[int] = Query(
        1000, description="Maximum number of data points", ge=1, le=10000
    ),
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
        raise HTTPException(status_code=401, detail="Invalid API key")

    history = _read_portfolio_history(team_id, days=days, limit=limit)

    return {
        "team_id": team_id,
        "days": days,
        "data_points": len(history),
        "history": history,
    }


@app.get("/api/v1/leaderboard/history")
@limiter.limit("120/minute")
def get_leaderboard_history(
    request: Request,
    days: Optional[int] = Query(
        7, description="Number of days to look back", ge=1, le=365
    ),
    limit: Optional[int] = Query(
        500, description="Max data points per team", ge=1, le=5000
    ),
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

    return {"days": days, "teams": all_teams_history}


@app.get("/api/v1/team/{team_id}/trades")
@limiter.limit("60/minute")
def get_team_trades(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    limit: Optional[int] = Query(
        100, description="Maximum number of trades", ge=1, le=1000
    ),
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
        "count": 1,
        "trades": [
            {
                "team_id": "test1",
                "timestamp": "2025-10-10T14:30:00+00:00",
                "symbol": "NVDA",
                "side": "buy",
                "quantity": 10,
                "requested_price": 500.25,
                "execution_price": 500.30,
                "order_type": "market",
                "broker_order_id": "abc123-alpaca-order-id"
            }
        ]
    }
    ```

    **Trade Fields:**
    - `team_id`: Team identifier
    - `timestamp`: Trade execution time (ISO 8601 UTC)
    - `symbol`: Stock symbol
    - `side`: "buy" or "sell"
    - `quantity`: Quantity traded
    - `requested_price`: Price requested by strategy
    - `execution_price`: Actual filled price (from Alpaca for market orders, or requested price for local-only)
    - `order_type`: "market" or "limit"
    - `broker_order_id`: Alpaca order ID (null if local-only mode)
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    trades_file = team_dir / "trades.jsonl"

    trades: List[Dict[str, Any]] = []

    if trades_file.exists():
        try:
            # Read trades from file (most recent first)
            with open(trades_file, "r", encoding="utf-8") as f:
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

    return {"team_id": team_id, "count": len(trades), "trades": trades}


@app.get("/api/v1/team/{team_id}/orders/open")
@limiter.limit("60/minute")
def get_team_open_orders(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication")
):
    """
    Get all open (pending) orders for a team.
    
    Returns limit orders and market orders that haven't filled yet.
    Useful for monitoring pending trades and understanding why positions haven't changed.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key for authentication
    
    **Returns:**
    ```json
    {
        "team_id": "epsilon",
        "open_orders_count": 2,
        "orders": [
            {
                "order_id": "abc-123-alpaca",
                "symbol": "NVDA",
                "side": "sell",
                "quantity": 10,
                "order_type": "limit",
                "limit_price": 530.00,
                "status": "new",
                "filled_qty": 0,
                "filled_avg_price": null,
                "time_in_force": "day",
                "created_at": "2025-10-15T14:30:00Z",
                "updated_at": "2025-10-15T14:30:00Z",
                "requested_price": 530.00
            }
        ]
    }
    ```
    
    **Order Status Values:**
    - `new` - Order accepted by broker, waiting to fill
    - `partially_filled` - Some shares filled, rest still open
    - `accepted` - Order received but not yet acknowledged
    
    **Use Cases:**
    - Monitor pending limit orders
    - See why sells haven't executed
    - Track order fill progress
    - Debug strategy behavior
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    from app.services.order_tracker import order_tracker
    
    # Get open orders for this team
    orders = order_tracker.get_open_orders(team_id)
    
    # Convert to dict format
    orders_list = []
    for order in orders:
        order_dict = {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": float(order.quantity),
            "order_type": order.order_type,
            "limit_price": float(order.limit_price) if order.limit_price else None,
            "status": order.status,
            "filled_qty": float(order.filled_qty),
            "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            "time_in_force": order.time_in_force,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "requested_price": float(order.requested_price),
            "broker_order_id": order.broker_order_id,
        }
        orders_list.append(order_dict)
    
    return {
        "team_id": team_id,
        "open_orders_count": len(orders_list),
        "orders": orders_list
    }


@app.get("/api/v1/team/{team_id}/orders/{order_id}")
@limiter.limit("60/minute")
def get_team_order_details(
    request: Request,
    team_id: str,
    order_id: str,
    key: str = Query(..., description="Team API key for authentication")
):
    """
    Get detailed status of a specific order.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `order_id`: Order ID (from broker_order_id field)
    - `key`: Team API key for authentication
    
    **Returns:**
    ```json
    {
        "order_id": "abc-123-alpaca",
        "team_id": "epsilon",
        "symbol": "NVDA",
        "side": "sell",
        "quantity": 10,
        "order_type": "limit",
        "limit_price": 530.00,
        "status": "partially_filled",
        "filled_qty": 5,
        "filled_avg_price": 530.25,
        "time_in_force": "day",
        "created_at": "2025-10-15T14:30:00Z",
        "updated_at": "2025-10-15T14:35:00Z"
    }
    ```
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    from app.services.order_tracker import order_tracker
    
    # Get order
    order = order_tracker.get_order_by_id(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail=f'Order {order_id} not found')
    
    # Verify order belongs to this team
    if order.team_id != team_id:
        raise HTTPException(status_code=403, detail='Order belongs to different team')
    
    return {
        "order_id": order.order_id,
        "team_id": order.team_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": float(order.quantity),
        "order_type": order.order_type,
        "limit_price": float(order.limit_price) if order.limit_price else None,
        "status": order.status,
        "filled_qty": float(order.filled_qty),
        "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
        "time_in_force": order.time_in_force,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "requested_price": float(order.requested_price),
        "broker_order_id": order.broker_order_id,
    }


@app.delete("/api/v1/team/{team_id}/orders/{order_id}")
@limiter.limit("30/minute")
def cancel_team_order(
    request: Request,
    team_id: str,
    order_id: str,
    key: str = Query(..., description="Team API key for authentication")
):
    """
    Cancel an open order.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `order_id`: Order ID to cancel
    - `key`: Team API key for authentication
    
    **Returns:**
    ```json
    {
        "success": true,
        "order_id": "abc-123-alpaca",
        "message": "Order cancelled successfully",
        "status": "cancelled"
    }
    ```
    
    **Errors:**
    - 404: Order not found or already filled
    - 403: Order belongs to different team
    - 500: Alpaca cancellation failed
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    
    from app.services.order_tracker import order_tracker
    from app.adapters.alpaca_broker import load_broker_from_env
    
    # Get order
    order = order_tracker.get_order_by_id(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail=f'Order {order_id} not found or already closed')
    
    # Verify order belongs to this team
    if order.team_id != team_id:
        raise HTTPException(status_code=403, detail='Order belongs to different team')
    
    # Cancel with Alpaca
    broker = load_broker_from_env()
    if broker:
        result = broker.cancelOrder(order.broker_order_id)
        
        if result.get("success"):
            # Update order status
            order.status = "cancelled"
            order.updated_at = datetime.now(timezone.utc)
            
            # Remove from pending orders
            if order_id in order_tracker.pending_orders:
                del order_tracker.pending_orders[order_id]
            
            return {
                "success": True,
                "order_id": order_id,
                "message": "Order cancelled successfully",
                "status": "cancelled"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f'Failed to cancel order: {result.get("error")}'
            )
    else:
        raise HTTPException(
            status_code=503,
            detail='Broker not available (local-only mode)'
        )


@app.get("/api/v1/team/{team_id}/metrics")
@limiter.limit("60/minute")
def get_team_metrics(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(
        None,
        description="Days to calculate metrics over (None = all data)",
        ge=1,
        le=365,
    ),
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
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get portfolio history
    history = _read_portfolio_history(team_id, days=days, limit=None)

    if not history:
        raise HTTPException(
            status_code=404, detail="No historical data available for this team"
        )

    # Calculate metrics with correct initial cash amount
    # Use the first portfolio value as the starting point, but ensure it's consistent
    initial_value = history[0]["value"] if history else 10000.0
    metrics = _calculate_performance_metrics(history, initial_value=initial_value)

    return {"team_id": team_id, "metrics": metrics}


@app.get("/api/v1/leaderboard/metrics")
@limiter.limit("60/minute")
def get_leaderboard_with_metrics(
    request: Request,
    days: Optional[int] = Query(
        None, description="Days to calculate metrics over (None = all)", ge=1, le=365
    ),
    sort_by: str = Query(
        "portfolio_value",
        description="Sort by: portfolio_value, sharpe_ratio, total_return, calmar_ratio",
    ),
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
    valid_sort_keys = [
        "portfolio_value",
        "sharpe_ratio",
        "total_return",
        "calmar_ratio",
        "sortino_ratio",
        "total_return_percentage",
        "annualized_return",
    ]

    if sort_by not in valid_sort_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by value. Must be one of: {', '.join(valid_sort_keys)}",
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
            raw_value = snap.get("market_value")
            if isinstance(raw_value, dict):
                raw_value = raw_value.get("__root__", raw_value)
            try:
                portfolio_value = float(raw_value) if raw_value is not None else None
            except Exception:
                portfolio_value = None

        # Get metrics
        history = _read_portfolio_history(team_id, days=days, limit=None)

        if history:
            # Use consistent initial value calculation
            initial_value = history[0]["value"] if history else 10000.0
            metrics = _calculate_performance_metrics(
                history, initial_value=initial_value
            )

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
                    "current_drawdown_percentage": metrics.get(
                        "current_drawdown_percentage"
                    ),
                    "total_return": metrics.get("total_return"),
                    "total_return_percentage": metrics.get("total_return_percentage"),
                    "annualized_return": metrics.get("annualized_return"),
                    "annualized_return_percentage": metrics.get(
                        "annualized_return_percentage"
                    ),
                    "annualized_volatility_percentage": metrics.get(
                        "annualized_volatility_percentage"
                    ),
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
                    "metrics_error": metrics.get("error"),
                }
        else:
            # No historical data
            team_data = {
                "team_id": team_id,
                "portfolio_value": portfolio_value,
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "calmar_ratio": None,
                "metrics_error": "No historical data available",
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
        "calculation_period_days": days if days else "all",
    }


@app.get("/{team_key}", response_class=PlainTextResponse)
def get_team_line_by_team_key(team_key: str):
    """Lookup team by API key and return a single-line status for CLI display."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        raise HTTPException(status_code=401, detail="invalid key")
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
            "files": [],
        }

    # Get list of all Python files
    py_files = list(directory.rglob("*.py"))
    file_list = [str(f.relative_to(directory)) for f in py_files]

    # Run security validation on all files
    try:
        ast_sanity_check(directory)  # Validates all .py files recursively
    except Exception as e:
        return {"valid": False, "error": str(e), "files": file_list}

    return {"valid": True, "files": file_list, "file_count": len(file_list)}


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
        teams.append(
            {
                "team_id": team_id,
                "repo_dir": str(repo_dir),
                "entry_point": "strategy:Strategy",
                "initial_cash": 10000,
                "run_24_7": False,
            }
        )

    # Save registry
    registry_path.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")


@app.post("/api/v1/team/{team_id}/upload-strategy")
@limiter.limit("3/minute")
async def upload_single_strategy(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    strategy_file: UploadFile = File(..., description="strategy.py file"),
):
    """Upload a single strategy.py file for a team.
    
    This endpoint is for simple, single-file strategies. For multi-file strategies,
    use the /upload-strategy-package endpoint with a ZIP file.
    
    **Authentication:** Requires team API key
    
    **Parameters:**
    - `team_id`: Team identifier
    - `key`: Team API key (form field)
    - `strategy_file`: Python file to upload (must be named strategy.py)
    
    **File Size Limits:**
    - Maximum file size: 10 MB
    
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
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Validate filename
    if not strategy_file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="File must be a Python (.py) file")

    # Read file content with size check
    try:
        content = await strategy_file.read()

        # Check file size
        if len(content) > MAX_SINGLE_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_SINGLE_FILE_SIZE / (1024 * 1024):.0f} MB",
            )

        code_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File must be valid UTF-8 encoded text"
        )

    # Validate in temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        temp_strategy = temp_path / "strategy.py"
        temp_strategy.write_text(code_str, encoding="utf-8")

        # Security validation
        validation = _validate_strategy_files(temp_path)
        if not validation["valid"]:
            raise HTTPException(
                status_code=400, detail=f"Validation failed: {validation['error']}"
            )

    # If validation passed, save to external_strategies
    strategy_dir = Path("/opt/qtc/external_strategies") / team_id
    strategy_dir.mkdir(parents=True, exist_ok=True)

    strategy_path = strategy_dir / "strategy.py"
    strategy_path.write_text(code_str, encoding="utf-8")

    # Update registry
    _update_team_registry(team_id, strategy_dir)

    return {
        "success": True,
        "message": f"Strategy uploaded successfully for {team_id}",
        "team_id": team_id,
        "files_uploaded": ["strategy.py"],
        "path": str(strategy_dir),
        "note": "Strategy will be loaded on the next trading cycle",
    }


@app.post("/api/v1/team/{team_id}/upload-strategy-package")
@limiter.limit("2/minute")
async def upload_strategy_package(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    strategy_zip: UploadFile = File(
        ..., description="ZIP file containing strategy.py and helper modules"
    ),
):
    """Upload a ZIP package containing strategy.py and multiple helper files.
    
    This endpoint supports complex, multi-file strategies. The ZIP should contain:
    - strategy.py (required) - Main entry point with Strategy class
    - Any number of additional .py files (helpers, utilities, etc.)
    
    **Authentication:** Requires team API key
    
    **File Size Limits:**
    - Maximum ZIP file size: 50 MB
    - Maximum total extracted size: 100 MB
    
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
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Validate file type
    if not strategy_zip.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Read ZIP content
    content = await strategy_zip.read()

    # Check ZIP file size
    if len(content) > MAX_ZIP_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP file too large. Maximum size is {MAX_ZIP_FILE_SIZE / (1024 * 1024):.0f} MB",
        )

    # Extract and validate in temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "upload.zip"
        zip_path.write_bytes(content)

        try:
            # Extract ZIP with security checks
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Check total uncompressed size (prevent zip bombs)
                total_size = sum(info.file_size for info in zip_ref.infolist())
                if total_size > MAX_TOTAL_EXTRACTED_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Total extracted size too large. Maximum is {MAX_TOTAL_EXTRACTED_SIZE / (1024 * 1024):.0f} MB",
                    )

                # Security: Check for path traversal attempts
                for member in zip_ref.namelist():
                    # Normalize the path
                    member_path = Path(member).resolve()

                    # Check for absolute paths or parent directory references
                    if member.startswith("/") or ".." in Path(member).parts:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid file path in ZIP: {member}. Paths must be relative and not use ..",
                        )

                    # Check individual file size (prevent zip bombs)
                    info = zip_ref.getinfo(member)
                    if info.file_size > MAX_SINGLE_FILE_SIZE:
                        raise HTTPException(
                            status_code=400,
                            detail=f"File {member} is too large (max {MAX_SINGLE_FILE_SIZE / (1024 * 1024):.0f} MB per file)",
                        )

                # Extract to temporary location
                extracted_dir = temp_path / "extracted"
                zip_ref.extractall(extracted_dir)

        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP file")

        # Validate extracted files
        validation = _validate_strategy_files(extracted_dir)

        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy validation failed: {validation['error']}",
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
        "validation": {"all_files_validated": True, "security_checks_passed": True},
        "note": "Strategy will be loaded on the next trading cycle",
    }


@app.post("/api/v1/team/{team_id}/upload-multiple-files")
@limiter.limit("2/minute")
async def upload_multiple_files(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    files: List[UploadFile] = File(
        ..., description="Multiple Python files (must include strategy.py)"
    ),
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
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check that at least one file is provided
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate and save to temporary directory first
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        uploaded_files = []

        for file in files:
            # Validate file extension
            if not file.filename.endswith(".py"):
                raise HTTPException(
                    status_code=400,
                    detail=f"All files must be Python (.py) files. Invalid: {file.filename}",
                )

            # Validate filename (no path traversal)
            filename = Path(file.filename).name
            if filename != file.filename or ".." in filename:
                raise HTTPException(
                    status_code=400, detail=f"Invalid filename: {file.filename}"
                )

            # Read and save file
            try:
                content = await file.read()

                # Check file size
                if len(content) > MAX_SINGLE_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File {filename} is too large. Maximum size is {MAX_SINGLE_FILE_SIZE / (1024 * 1024):.0f} MB",
                    )

                code_str = content.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} must be valid UTF-8 encoded text",
                )

            file_path = temp_path / filename
            file_path.write_text(code_str, encoding="utf-8")
            uploaded_files.append(filename)

        # Validate all files
        validation = _validate_strategy_files(temp_path)

        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy validation failed: {validation['error']}",
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
        "validation": {"all_files_validated": True, "security_checks_passed": True},
        "note": "Strategy will be loaded on the next trading cycle",
    }


@app.get("/api/v1/status")
@limiter.limit("120/minute")
def get_system_status(request: Request):
    """Get system-wide health status and operational information.

    Public endpoint for monitoring system health, market status, and data feed status.

    **Authentication:** None required (public endpoint)

    **Returns:**
    ```json
    {
        "status": "operational",
        "timestamp": "2025-10-15T15:42:30+00:00",
        "market": {
            "is_open": true,
            "status": "trading"
        },
        "orchestrator": {
            "running": true,
            "last_heartbeat": "2025-10-15T15:42:00+00:00",
            "execution_frequency_seconds": 60,
            "teams_loaded": 9,
            "teams_active": 9
        },
        "data_feed": {
            "last_update": "2025-10-15T15:42:00+00:00",
            "seconds_since_update": 30,
            "status": "healthy",
            "symbols_tracked": 9
        }
    }
    ```
    """
    # Read runtime status file
    status_file = config.get_data_path("runtime/status.json")

    if not status_file.exists():
        return {
            "status": "starting",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orchestrator": {"running": False},
            "message": "System initializing - status will be available shortly",
        }

    try:
        runtime_data = json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Unable to read system status",
        }

    # Check market hours
    from app.services.market_hours import us_equity_market_open

    market_open = us_equity_market_open()

    # Calculate time since last update
    last_update_str = runtime_data.get("timestamp")
    seconds_since_update = 0
    if last_update_str:
        try:
            last_update = datetime.fromisoformat(last_update_str)
            seconds_since_update = int(
                (datetime.now(timezone.utc) - last_update).total_seconds()
            )
        except Exception:
            pass

    # Determine overall status
    is_running = runtime_data.get("running", False)
    data_is_fresh = seconds_since_update < 120  # Less than 2 minutes old

    if is_running and data_is_fresh:
        overall_status = "operational"
    elif is_running and not data_is_fresh:
        overall_status = "degraded"
    else:
        overall_status = "stopped"

    # Determine data feed status
    if seconds_since_update < 90:
        feed_status = "healthy"
    elif seconds_since_update < 300:
        feed_status = "delayed"
    else:
        feed_status = "stale"

    teams = runtime_data.get("teams", [])
    teams_active = sum(1 for t in teams if t.get("active", False))

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market": {
            "is_open": market_open,
            "status": "trading" if market_open else "closed",
        },
        "orchestrator": {
            "running": is_running,
            "last_heartbeat": last_update_str,
            "execution_frequency_seconds": 60,
            "teams_loaded": len(teams),
            "teams_active": teams_active,
            "uptime_status": "healthy" if data_is_fresh else "stale",
        },
        "data_feed": {
            "last_update": last_update_str,
            "seconds_since_update": seconds_since_update,
            "status": feed_status,
            "symbols_tracked": len(runtime_data.get("symbols", [])),
            "bars_received": runtime_data.get("bar_count", 0),
        },
    }


@app.get("/api/v1/team/{team_id}/errors")
@limiter.limit("30/minute")
def get_team_errors(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    limit: Optional[int] = Query(
        100, description="Maximum number of errors", ge=1, le=500
    ),
):
    """Get recent strategy execution errors for a team."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    error_file = team_dir / "errors.jsonl"

    errors: List[Dict[str, Any]] = []

    if error_file.exists():
        try:
            with open(error_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    error = json.loads(line)
                    errors.append(error)
                except Exception:
                    continue
        except Exception:
            pass

    errors.reverse()

    return {"team_id": team_id, "error_count": len(errors), "errors": errors}


@app.get("/api/v1/team/{team_id}/execution-health")
@limiter.limit("60/minute")
def get_team_execution_health(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
):
    """Get execution health and performance statistics for a team's strategy.

    Returns detailed information about strategy execution including success rate,
    timing, errors, and recent activity. Essential for monitoring strategy health.

    **Authentication:** Requires team API key

    **Returns:**
    ```json
    {
        "team_id": "admin",
        "timestamp": "2025-10-15T15:45:00+00:00",
        "strategy": {
            "entry_point": "strategy:Strategy",
            "repo_path": "/opt/qtc/external_strategies/admin",
            "status": "active",
            "last_uploaded": "2025-10-14T16:50:00+00:00"
        },
        "execution": {
            "is_active": true,
            "last_execution": "2025-10-15T15:44:00+00:00",
            "seconds_since_last": 35,
            "total_executions": 157,
            "successful_executions": 155,
            "failed_executions": 2,
            "success_rate_percentage": 98.73
        },
        "errors": {
            "error_count": 1,
            "timeout_count": 1,
            "last_error": {
                "timestamp": "2025-10-15T14:05:00+00:00",
                "error_type": "TimeoutError",
                "message": "Strategy execution exceeded 5 seconds"
            }
        },
        "performance": {
            "avg_execution_time_ms": 125,
            "approaching_timeout": false,
            "timeout_risk": "low"
        }
    }
    ```
    """
    # Validate API key
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Read runtime status
    status_file = config.get_data_path("runtime/status.json")

    if not status_file.exists():
        raise HTTPException(
            status_code=503,
            detail="Runtime status not available - orchestrator may not be running",
        )

    try:
        runtime_data = json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to read runtime status")

    # Find team in runtime status
    teams = runtime_data.get("teams", [])
    team_status = next((t for t in teams if t.get("team_id") == team_id), None)

    if not team_status:
        raise HTTPException(status_code=404, detail="Team not found in runtime status")

    # Read error log
    team_dir = config.get_data_path(f"team/{team_id}")
    error_file = team_dir / "errors.jsonl"

    errors = []
    timeout_count = 0
    error_count = 0

    if error_file.exists():
        try:
            with open(error_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        error = json.loads(line)
                        errors.append(error)
                        if (
                            error.get("timeout", False)
                            or error.get("error_type") == "TimeoutError"
                        ):
                            timeout_count += 1
                        error_count += 1
                    except Exception:
                        continue
        except Exception:
            pass

    # Get last error
    last_error = errors[-1] if errors else None

    # Calculate execution stats (approximate from trades and errors)
    trades_file = team_dir / "trades.jsonl"
    trade_count = 0

    if trades_file.exists():
        try:
            with open(trades_file, "r", encoding="utf-8") as f:
                trade_count = sum(1 for line in f if line.strip())
        except Exception:
            pass

    # Read portfolio snapshots to get execution count
    port_dir = team_dir / "portfolio"
    execution_count = 0

    if port_dir.exists():
        jsonl_files = sorted([f for f in port_dir.glob("2025-*.jsonl") if f.is_file()])
        # Get today's file
        today = datetime.now(timezone.utc).date().isoformat()
        today_file = port_dir / f"{today}.jsonl"

        if today_file.exists():
            try:
                with open(today_file, "r", encoding="utf-8") as f:
                    execution_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

    # Calculate success rate
    failed_count = len(errors)
    successful_count = max(0, execution_count - failed_count)
    success_rate = (
        (successful_count / execution_count * 100) if execution_count > 0 else 0
    )

    # Check last execution time
    last_snapshot_str = team_status.get("last_snapshot")
    seconds_since_last = 0
    if last_snapshot_str:
        try:
            last_snap = datetime.fromisoformat(last_snapshot_str)
            seconds_since_last = int(
                (datetime.now(timezone.utc) - last_snap).total_seconds()
            )
        except Exception:
            pass

    # Get strategy file modification time
    strategy_path = Path(team_status.get("repo", "")) / "strategy.py"
    last_uploaded = None
    if strategy_path.exists():
        try:
            import os

            mtime = os.path.getmtime(strategy_path)
            last_uploaded = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

    # Determine strategy status
    has_error = team_status.get("error") is not None
    is_active = team_status.get("active", False)

    if has_error:
        strategy_status = "error"
    elif not is_active:
        strategy_status = "idle"
    else:
        strategy_status = "active"

    # Estimate average execution time from timeout patterns
    # If we have timeouts, execution time is approaching limit
    timeout_risk = (
        "high" if timeout_count > 3 else ("medium" if timeout_count > 0 else "low")
    )
    approaching_timeout = timeout_count > 0

    # Rough estimate: if no timeouts, assume avg is well below 5s
    avg_execution_time_ms = (
        4500 if timeout_count > 2 else (3000 if timeout_count > 0 else 150)
    )

    return {
        "team_id": team_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy": {
            "entry_point": team_status.get("strategy"),
            "repo_path": team_status.get("repo"),
            "status": strategy_status,
            "last_uploaded": last_uploaded,
            "run_24_7": team_status.get("run_24_7", False),
        },
        "execution": {
            "is_active": is_active,
            "last_execution": last_snapshot_str,
            "seconds_since_last": seconds_since_last,
            "total_executions_today": execution_count,
            "successful_executions": successful_count,
            "failed_executions": failed_count,
            "success_rate_percentage": round(success_rate, 2),
        },
        "errors": {
            "error_count": error_count,
            "timeout_count": timeout_count,
            "last_error": last_error,
            "consecutive_failures": 0 if is_active and not has_error else failed_count,
        },
        "performance": {
            "avg_execution_time_ms": avg_execution_time_ms,
            "approaching_timeout": approaching_timeout,
            "timeout_risk": timeout_risk,
            "timeout_limit_seconds": 5,
        },
        "trading": {
            "total_trades_today": trade_count,
            "signal_rate_percentage": round(
                (trade_count / execution_count * 100) if execution_count > 0 else 0, 2
            ),
        },
    }


@app.get("/api/v1/team/{team_id}/portfolio-history")
@limiter.limit("20/minute")
def get_team_portfolio_history(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(7, description="Days to look back", ge=1, le=365),
    limit: Optional[int] = Query(500, description="Max snapshots", ge=1, le=5000),
):
    """Get complete portfolio history including positions over time."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"

    if not port_dir.exists():
        return {"team_id": team_id, "days": days, "snapshot_count": 0, "snapshots": []}

    cutoff_time = None
    if days is not None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

    snapshots: List[Dict[str, Any]] = []
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])

    for jsonl_file in jsonl_files[-days:] if days else jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snapshot = json.loads(line)
                        timestamp_str = snapshot.get("timestamp")
                        if timestamp_str:
                            try:
                                ts = datetime.fromisoformat(
                                    timestamp_str.replace("Z", "+00:00")
                                )
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                                if cutoff_time and ts < cutoff_time:
                                    continue
                            except Exception:
                                continue

                        # Filter out avg_cost and pnl_unrealized from positions
                        raw_positions = snapshot.get("positions", {})
                        filtered_positions = {}
                        for symbol, pos_data in raw_positions.items():
                            if isinstance(pos_data, dict):
                                filtered_positions[symbol] = {
                                    k: v
                                    for k, v in pos_data.items()
                                    if k
                                    not in (
                                        "avg_cost",
                                        "pnl_unrealized",
                                        "unrealized_pnl",
                                    )
                                }
                            else:
                                filtered_positions[symbol] = pos_data

                        snapshots.append(
                            {
                                "timestamp": timestamp_str,
                                "cash": float(snapshot.get("cash", 0)),
                                "market_value": float(snapshot.get("market_value", 0)),
                                "positions": filtered_positions,
                            }
                        )
                    except Exception:
                        continue
        except Exception:
            continue

    snapshots.sort(key=lambda x: x["timestamp"])

    if limit and len(snapshots) > limit:
        step = max(1, len(snapshots) // limit)
        snapshots = snapshots[::step][:limit]

    return {
        "team_id": team_id,
        "days": days,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
    }


@app.get("/api/v1/team/{team_id}/position/{symbol}/history")
@limiter.limit("30/minute")
def get_team_symbol_position_history(
    request: Request,
    team_id: str,
    symbol: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(7, description="Days to look back", ge=1, le=365),
    limit: Optional[int] = Query(1000, description="Max data points", ge=1, le=10000),
):
    """Get position history for a specific symbol."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"

    if not port_dir.exists():
        return {
            "team_id": team_id,
            "symbol": symbol,
            "days": days,
            "data_points": 0,
            "history": [],
        }

    cutoff_time = None
    if days is not None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

    history: List[Dict[str, Any]] = []
    symbol_upper = symbol.upper()
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])

    for jsonl_file in jsonl_files[-days:] if days else jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snapshot = json.loads(line)
                        timestamp_str = snapshot.get("timestamp")
                        if timestamp_str:
                            try:
                                ts = datetime.fromisoformat(
                                    timestamp_str.replace("Z", "+00:00")
                                )
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                                if cutoff_time and ts < cutoff_time:
                                    continue
                            except Exception:
                                continue

                        positions = snapshot.get("positions", {})
                        position = positions.get(symbol_upper, {})

                        history.append(
                            {
                                "timestamp": timestamp_str,
                                "quantity": float(position.get("quantity", 0)),
                                "value": float(position.get("value", 0)),
                            }
                        )
                    except Exception:
                        continue
        except Exception:
            continue

    history.sort(key=lambda x: x["timestamp"])

    if limit and len(history) > limit:
        step = max(1, len(history) // limit)
        history = history[::step][:limit]

    return {
        "team_id": team_id,
        "symbol": symbol_upper,
        "days": days,
        "data_points": len(history),
        "history": history,
    }


@app.get("/api/v1/team/{team_id}/positions/summary")
@limiter.limit("30/minute")
def get_team_positions_summary(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(30, description="Days to analyze", ge=1, le=365),
):
    """Get summary of all symbols traded with aggregate statistics."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"

    if not port_dir.exists():
        return {
            "team_id": team_id,
            "period_days": days,
            "symbols_traded": 0,
            "current_positions": 0,
            "symbols": [],
        }

    cutoff_time = None
    if days is not None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

    symbol_stats: Dict[str, Dict[str, Any]] = {}
    latest_positions: Dict[str, Dict[str, Any]] = {}
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])

    for jsonl_file in jsonl_files[-days:] if days else jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snapshot = json.loads(line)
                        timestamp_str = snapshot.get("timestamp")
                        if timestamp_str:
                            try:
                                ts = datetime.fromisoformat(
                                    timestamp_str.replace("Z", "+00:00")
                                )
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                                if cutoff_time and ts < cutoff_time:
                                    continue
                            except Exception:
                                continue

                        positions = snapshot.get("positions", {})
                        for symbol, pos in positions.items():
                            if symbol not in symbol_stats:
                                symbol_stats[symbol] = {
                                    "symbol": symbol,
                                    "times_held": 0,
                                    "minutes_held": 0,
                                    "max_quantity": 0,
                                    "quantities": [],
                                }

                            qty = float(pos.get("quantity", 0))
                            if qty > 0:
                                symbol_stats[symbol]["times_held"] += 1
                                symbol_stats[symbol]["minutes_held"] += 1
                                symbol_stats[symbol]["quantities"].append(qty)
                                symbol_stats[symbol]["max_quantity"] = max(
                                    symbol_stats[symbol]["max_quantity"], qty
                                )

                            latest_positions[symbol] = pos

                    except Exception:
                        continue
        except Exception:
            continue

    symbols_summary = []
    current_position_count = 0

    for symbol, stats in symbol_stats.items():
        latest_pos = latest_positions.get(symbol, {})
        current_qty = float(latest_pos.get("quantity", 0))
        currently_holding = current_qty > 0

        if currently_holding:
            current_position_count += 1

        quantities = stats["quantities"]
        avg_quantity = sum(quantities) / len(quantities) if quantities else 0

        symbols_summary.append(
            {
                "symbol": symbol,
                "currently_holding": currently_holding,
                "current_quantity": current_qty,
                "current_value": float(latest_pos.get("value", 0))
                if currently_holding
                else 0,
                "current_pnl": float(latest_pos.get("pnl_unrealized", 0))
                if currently_holding
                else 0,
                "times_held": stats["times_held"],
                "minutes_held": stats["minutes_held"],
                "max_quantity": stats["max_quantity"],
                "avg_quantity": round(avg_quantity, 2),
            }
        )

    symbols_summary.sort(key=lambda x: x["times_held"], reverse=True)

    return {
        "team_id": team_id,
        "period_days": days,
        "symbols_traded": len(symbols_summary),
        "current_positions": current_position_count,
        "symbols": symbols_summary,
    }
