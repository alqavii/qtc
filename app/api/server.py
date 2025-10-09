from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional, List
import asyncio
import threading
from pathlib import Path
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


@app.get('/{team_key}', response_class=PlainTextResponse)
def get_team_line_by_team_key(team_key: str):
    """Lookup team by API key and return a single-line status for CLI display."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        raise HTTPException(status_code=401, detail='invalid key')
    return _team_line(team_id)
