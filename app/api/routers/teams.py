"""
Team-specific endpoints.

Handles all /api/v1/team/{team_id}/* routes.
"""

import json
import shutil
import tempfile
import zipfile
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, Request, Query, HTTPException, File, UploadFile, Form

from app.config.environments import config
from app.config.settings import (
    MAX_SINGLE_FILE_SIZE,
    MAX_ZIP_FILE_SIZE,
    MAX_TOTAL_EXTRACTED_SIZE,
)
from app.services.auth import auth_manager
from app.api.deps import (
    tail_jsonl,
    calculate_performance_metrics,
    read_portfolio_history,
)

router = APIRouter(prefix="/api/v1/team", tags=["Teams"])


@router.get("/{team_id}/history")
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
    """Get historical portfolio values for a specific team."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    history = read_portfolio_history(team_id, days=days, limit=limit)

    return {
        "team_id": team_id,
        "days": days,
        "data_points": len(history),
        "history": history,
    }


@router.get("/{team_id}/trades")
def get_team_trades(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    limit: Optional[int] = Query(
        100, description="Maximum number of trades", ge=1, le=1000
    ),
):
    """Get recent trade history for a specific team."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    trades_file = team_dir / "trades.jsonl"

    trades: List[Dict[str, Any]] = []

    if trades_file.exists():
        try:
            with open(trades_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

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

    trades.reverse()

    return {"team_id": team_id, "count": len(trades), "trades": trades}


@router.get("/{team_id}/orders/open")
def get_team_open_orders(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
):
    """Get all open (pending) orders for a team."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    from app.services.order_tracker import order_tracker

    open_orders = order_tracker.get_open_orders(team_id)

    orders_data = []
    for order in open_orders:
        order_dict = {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": str(order.quantity),
            "order_type": order.order_type,
            "limit_price": str(order.limit_price) if order.limit_price else None,
            "status": order.status,
            "filled_qty": str(order.filled_qty),
            "filled_avg_price": str(order.filled_avg_price)
            if order.filled_avg_price
            else None,
            "time_in_force": order.time_in_force,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "requested_price": str(order.requested_price),
        }
        orders_data.append(order_dict)

    return {
        "team_id": team_id,
        "open_orders_count": len(orders_data),
        "orders": orders_data,
    }


@router.get("/{team_id}/orders/{order_id}")
def get_order_status(
    request: Request,
    team_id: str,
    order_id: str,
    key: str = Query(..., description="Team API key for authentication"),
):
    """Get detailed status of a specific order."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    from app.services.order_tracker import order_tracker

    order = order_tracker.get_order(order_id)

    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    if order.team_id != team_id:
        raise HTTPException(
            status_code=403, detail="Order belongs to a different team"
        )

    return {
        "order_id": order.order_id,
        "team_id": order.team_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": str(order.quantity),
        "order_type": order.order_type,
        "limit_price": str(order.limit_price) if order.limit_price else None,
        "status": order.status,
        "filled_qty": str(order.filled_qty),
        "filled_avg_price": str(order.filled_avg_price)
        if order.filled_avg_price
        else None,
        "time_in_force": order.time_in_force,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "requested_price": str(order.requested_price),
    }


@router.delete("/{team_id}/orders/{order_id}")
def cancel_order(
    request: Request,
    team_id: str,
    order_id: str,
    key: str = Query(..., description="Team API key for authentication"),
):
    """Cancel an open order."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    from app.services.order_tracker import order_tracker
    from app.adapters.alpaca_broker import load_broker_from_env

    order = order_tracker.get_order(order_id)

    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    if order.team_id != team_id:
        raise HTTPException(
            status_code=403, detail="Order belongs to a different team"
        )

    if order.status in ("filled", "cancelled", "rejected", "expired"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status '{order.status}'",
        )

    broker = load_broker_from_env()
    if broker:
        try:
            broker.cancelOrder(order_id)
            order_tracker.update_order_status(order_id, "cancelled")
            return {
                "success": True,
                "message": f"Order {order_id} cancelled successfully",
                "order_id": order_id,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to cancel order: {str(e)}"
            )
    else:
        order_tracker.update_order_status(order_id, "cancelled")
        return {
            "success": True,
            "message": f"Order {order_id} cancelled (local only - no broker connected)",
            "order_id": order_id,
        }


@router.get("/{team_id}/metrics")
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
    """Get comprehensive performance metrics for a team."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    history = read_portfolio_history(team_id, days=days)

    if not history:
        return {
            "team_id": team_id,
            "error": "No portfolio history available",
            "message": "Team has no recorded portfolio snapshots yet",
        }

    metrics = calculate_performance_metrics(history)

    return {
        "team_id": team_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_analyzed": days,
        **metrics,
    }


@router.get("/{team_id}/errors")
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

    return {"team_id": team_id, "count": len(errors), "errors": errors}


@router.get("/{team_id}/execution-health")
def get_team_execution_health(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
):
    """Get execution health and performance statistics for a team's strategy."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")

    trades_file = team_dir / "trades.jsonl"
    trade_count = 0
    if trades_file.exists():
        with open(trades_file, "r", encoding="utf-8") as f:
            trade_count = sum(1 for line in f if line.strip())

    error_file = team_dir / "errors.jsonl"
    error_count = 0
    recent_errors: List[Dict[str, Any]] = []
    if error_file.exists():
        with open(error_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            error_count = len([l for l in lines if l.strip()])
            for line in lines[-5:]:
                line = line.strip()
                if line:
                    try:
                        recent_errors.append(json.loads(line))
                    except Exception:
                        pass

    port_dir = team_dir / "portfolio"
    snapshot_count = 0
    if port_dir.exists():
        for f in port_dir.glob("*.jsonl"):
            with open(f, "r", encoding="utf-8") as fh:
                snapshot_count += sum(1 for line in fh if line.strip())

    status_file = config.get_data_path("runtime/status.json")
    last_execution = None
    strategy_active = False

    if status_file.exists():
        try:
            runtime_data = json.loads(status_file.read_text(encoding="utf-8"))
            teams = runtime_data.get("teams", [])
            for t in teams:
                if t.get("team_id") == team_id:
                    last_execution = t.get("last_snapshot")
                    strategy_active = t.get("active", False)
                    break
        except Exception:
            pass

    if error_count == 0:
        health_status = "healthy"
    elif error_count < 10:
        health_status = "degraded"
    else:
        health_status = "unhealthy"

    return {
        "team_id": team_id,
        "health_status": health_status,
        "strategy_active": strategy_active,
        "last_execution": last_execution,
        "statistics": {
            "total_trades": trade_count,
            "total_errors": error_count,
            "total_snapshots": snapshot_count,
            "error_rate": error_count / max(snapshot_count, 1),
        },
        "recent_errors": recent_errors,
    }


@router.get("/{team_id}/portfolio-history")
def get_team_portfolio_history(
    request: Request,
    team_id: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(7, description="Days to look back", ge=1, le=365),
    limit: Optional[int] = Query(500, description="Max snapshots", ge=1, le=5000),
):
    """Get detailed portfolio snapshots including positions over time."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"

    if not port_dir.exists():
        return {
            "team_id": team_id,
            "days": days,
            "snapshots": [],
            "message": "No portfolio history available",
        }

    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days) if days else None

    snapshots: List[Dict[str, Any]] = []
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snapshot = json.loads(line)
                        ts_str = snapshot.get("timestamp")
                        if ts_str and cutoff_time:
                            try:
                                ts = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00")
                                )
                                if ts < cutoff_time:
                                    continue
                            except Exception:
                                pass
                        snapshots.append(snapshot)
                    except Exception:
                        continue
        except Exception:
            continue

    snapshots.sort(key=lambda x: x.get("timestamp", ""))

    if limit and len(snapshots) > limit:
        step = max(1, len(snapshots) // limit)
        snapshots = snapshots[::step][:limit]

    return {
        "team_id": team_id,
        "days": days,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
    }


@router.get("/{team_id}/position/{symbol}/history")
def get_position_history(
    request: Request,
    team_id: str,
    symbol: str,
    key: str = Query(..., description="Team API key for authentication"),
    days: Optional[int] = Query(7, description="Days to look back", ge=1, le=365),
    limit: Optional[int] = Query(1000, description="Max data points", ge=1, le=10000),
):
    """Get historical data for a specific position."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"
    symbol = symbol.upper()

    if not port_dir.exists():
        return {
            "team_id": team_id,
            "symbol": symbol,
            "history": [],
            "message": "No portfolio history available",
        }

    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days) if days else None

    position_history: List[Dict[str, Any]] = []
    jsonl_files = sorted([f for f in port_dir.glob("*.jsonl") if f.is_file()])

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snapshot = json.loads(line)
                        ts_str = snapshot.get("timestamp")
                        if ts_str and cutoff_time:
                            try:
                                ts = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00")
                                )
                                if ts < cutoff_time:
                                    continue
                            except Exception:
                                pass

                        positions = snapshot.get("positions", {})
                        pos = positions.get(symbol)
                        if pos:
                            position_history.append(
                                {
                                    "timestamp": ts_str,
                                    "quantity": pos.get("quantity"),
                                    "value": pos.get("value"),
                                    "avg_cost": pos.get("avg_cost"),
                                    "side": pos.get("side"),
                                }
                            )
                        else:
                            position_history.append(
                                {
                                    "timestamp": ts_str,
                                    "quantity": 0,
                                    "value": 0,
                                    "avg_cost": None,
                                    "side": None,
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            continue

    position_history.sort(key=lambda x: x.get("timestamp", ""))

    if limit and len(position_history) > limit:
        step = max(1, len(position_history) // limit)
        position_history = position_history[::step][:limit]

    return {
        "team_id": team_id,
        "symbol": symbol,
        "days": days,
        "data_points": len(position_history),
        "history": position_history,
    }


@router.get("/{team_id}/positions/summary")
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
    for symbol, stats in symbol_stats.items():
        quantities = stats["quantities"]
        avg_quantity = sum(quantities) / len(quantities) if quantities else 0

        current_pos = latest_positions.get(symbol, {})
        current_qty = float(current_pos.get("quantity", 0))

        symbols_summary.append(
            {
                "symbol": symbol,
                "currently_held": current_qty > 0,
                "current_quantity": current_qty,
                "current_value": current_pos.get("value"),
                "minutes_held": stats["minutes_held"],
                "max_quantity": stats["max_quantity"],
                "avg_quantity": round(avg_quantity, 2),
            }
        )

    symbols_summary.sort(key=lambda x: x["minutes_held"], reverse=True)

    current_count = sum(1 for s in symbols_summary if s["currently_held"])

    return {
        "team_id": team_id,
        "period_days": days,
        "symbols_traded": len(symbols_summary),
        "current_positions": current_count,
        "symbols": symbols_summary,
    }


# =============================================================================
# Strategy Upload Endpoints
# =============================================================================


@router.post("/{team_id}/upload-strategy")
async def upload_single_strategy(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    strategy_file: UploadFile = File(..., description="strategy.py file"),
):
    """Upload a single strategy.py file for a team."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not strategy_file.filename or not strategy_file.filename.endswith(".py"):
        raise HTTPException(
            status_code=400, detail="File must be a Python file (.py extension)"
        )

    content = await strategy_file.read()
    if len(content) > MAX_SINGLE_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_SINGLE_FILE_SIZE // (1024*1024)}MB",
        )

    from app.loaders.static_check import ast_sanity_check

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        strategy_path = temp_path / "strategy.py"
        strategy_path.write_bytes(content)

        try:
            ast_sanity_check(temp_path, entry_point="strategy:Strategy")
        except RuntimeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Security validation failed: {str(e)}",
            )

        strategies_root = Path("external_strategies")
        team_strategy_dir = strategies_root / team_id
        team_strategy_dir.mkdir(parents=True, exist_ok=True)

        final_path = team_strategy_dir / "strategy.py"
        final_path.write_bytes(content)

    return {
        "status": "success",
        "team_id": team_id,
        "message": "Strategy uploaded successfully",
        "file": "strategy.py",
        "size_bytes": len(content),
        "entry_point": "strategy:Strategy",
        "validation": {"all_files_validated": True, "security_checks_passed": True},
        "note": "Strategy will be loaded on the next trading cycle",
    }


@router.post("/{team_id}/upload-strategy-package")
async def upload_strategy_package(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    strategy_zip: UploadFile = File(
        ..., description="ZIP file containing strategy.py and helper modules"
    ),
):
    """Upload a ZIP package containing strategy and helper modules."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not strategy_zip.filename or not strategy_zip.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    content = await strategy_zip.read()
    if len(content) > MAX_ZIP_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP too large. Maximum size is {MAX_ZIP_FILE_SIZE // (1024*1024)}MB",
        )

    from app.loaders.static_check import ast_sanity_check

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "strategy.zip"
        zip_path.write_bytes(content)

        extract_path = temp_path / "extracted"
        extract_path.mkdir()

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > MAX_TOTAL_EXTRACTED_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Extracted size too large. Maximum is {MAX_TOTAL_EXTRACTED_SIZE // (1024*1024)}MB",
                    )

                for info in zf.infolist():
                    if info.filename.startswith("/") or ".." in info.filename:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid path in ZIP: {info.filename}",
                        )

                zf.extractall(extract_path)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid ZIP file")

        strategy_file = extract_path / "strategy.py"
        if not strategy_file.exists():
            subdirs = [d for d in extract_path.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                nested_strategy = subdirs[0] / "strategy.py"
                if nested_strategy.exists():
                    extract_path = subdirs[0]
                    strategy_file = nested_strategy

        if not strategy_file.exists():
            raise HTTPException(
                status_code=400,
                detail="ZIP must contain strategy.py at root level",
            )

        try:
            ast_sanity_check(extract_path, entry_point="strategy:Strategy")
        except RuntimeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Security validation failed: {str(e)}",
            )

        strategies_root = Path("external_strategies")
        team_strategy_dir = strategies_root / team_id

        if team_strategy_dir.exists():
            shutil.rmtree(team_strategy_dir)
        team_strategy_dir.mkdir(parents=True, exist_ok=True)

        files_copied = []
        for py_file in extract_path.glob("*.py"):
            dest = team_strategy_dir / py_file.name
            shutil.copy2(py_file, dest)
            files_copied.append(py_file.name)

    return {
        "status": "success",
        "team_id": team_id,
        "message": "Strategy package uploaded successfully",
        "files": files_copied,
        "file_count": len(files_copied),
        "entry_point": "strategy:Strategy",
        "validation": {"all_files_validated": True, "security_checks_passed": True},
        "note": "Strategy will be loaded on the next trading cycle",
    }


@router.post("/{team_id}/upload-multiple-files")
async def upload_multiple_files(
    request: Request,
    team_id: str,
    key: str = Form(..., description="Team API key for authentication"),
    files: List[UploadFile] = File(
        ..., description="Multiple Python files (must include strategy.py)"
    ),
):
    """Upload multiple Python files for a strategy."""
    if not auth_manager.validateTeam(team_id, key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    has_strategy = False
    for f in files:
        if not f.filename:
            raise HTTPException(status_code=400, detail="All files must have names")
        if not f.filename.endswith(".py"):
            raise HTTPException(
                status_code=400,
                detail=f"All files must be Python files: {f.filename}",
            )
        if f.filename == "strategy.py":
            has_strategy = True

    if not has_strategy:
        raise HTTPException(
            status_code=400,
            detail="Must include strategy.py file",
        )

    from app.loaders.static_check import ast_sanity_check

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        total_size = 0
        files_saved = []

        for upload_file in files:
            content = await upload_file.read()
            total_size += len(content)

            if total_size > MAX_TOTAL_EXTRACTED_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"Total size too large. Maximum is {MAX_TOTAL_EXTRACTED_SIZE // (1024*1024)}MB",
                )

            file_path = temp_path / upload_file.filename
            file_path.write_bytes(content)
            files_saved.append(upload_file.filename)

        try:
            ast_sanity_check(temp_path, entry_point="strategy:Strategy")
        except RuntimeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Security validation failed: {str(e)}",
            )

        strategies_root = Path("external_strategies")
        team_strategy_dir = strategies_root / team_id

        if team_strategy_dir.exists():
            shutil.rmtree(team_strategy_dir)
        team_strategy_dir.mkdir(parents=True, exist_ok=True)

        for py_file in temp_path.glob("*.py"):
            dest = team_strategy_dir / py_file.name
            shutil.copy2(py_file, dest)

    return {
        "status": "success",
        "team_id": team_id,
        "message": "Strategy files uploaded successfully",
        "files": files_saved,
        "file_count": len(files_saved),
        "total_size_bytes": total_size,
        "entry_point": "strategy:Strategy",
        "validation": {"all_files_validated": True, "security_checks_passed": True},
        "note": "Strategy will be loaded on the next trading cycle",
    }
