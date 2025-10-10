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


@app.get('/{team_key}', response_class=PlainTextResponse)
def get_team_line_by_team_key(team_key: str):
    """Lookup team by API key and return a single-line status for CLI display."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        raise HTTPException(status_code=401, detail='invalid key')
    return _team_line(team_id)
