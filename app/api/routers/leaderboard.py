"""
Leaderboard endpoints.
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse

from app.config.environments import config
from app.services.auth import auth_manager
from app.api.deps import (
    tail_jsonl,
    list_team_ids,
    calculate_performance_metrics,
    read_portfolio_history,
)

router = APIRouter(tags=["Leaderboard"])


def _team_line(team_id: str) -> str:
    """Format team status as a single line for CLI display."""
    team_dir = config.get_data_path(f"team/{team_id}")
    port_dir = team_dir / "portfolio"
    latest_json = None
    if port_dir.exists():
        files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
        if files:
            latest_json = files[-1]
    snapshot = tail_jsonl(latest_json) if latest_json else None
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


@router.get("/leaderboard")
def get_leaderboard(request: Request):
    """Get leaderboard of all teams sorted by portfolio value."""
    out: List[Dict[str, Any]] = []
    for tid in list_team_ids():
        team_dir = config.get_data_path(f"team/{tid}")
        port_dir = team_dir / "portfolio"
        latest_json = None
        if port_dir.exists():
            files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
            if files:
                latest_json = files[-1]
        snap = tail_jsonl(latest_json) if latest_json else None
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


@router.get("/{team_key}", response_class=PlainTextResponse)
def get_team_line_by_team_key(team_key: str):
    """Lookup team by API key and return a single-line status for CLI display."""
    team_id = auth_manager.findTeamByKey(team_key)
    if not team_id:
        return PlainTextResponse("Invalid key or team not found", status_code=401)
    return _team_line(team_id)


@router.get("/api/v1/leaderboard/history")
def get_leaderboard_history(
    request: Request,
    days: Optional[int] = Query(7, description="Number of days to look back", ge=1, le=365),
    limit: Optional[int] = Query(
        1000, description="Maximum number of data points per team", ge=1, le=10000
    ),
):
    """Get historical portfolio values for all teams.

    Returns time-series data for all teams to display comparative performance over time.

    **Parameters:**
    - `days`: Number of days to look back (default: 7, max: 365)
    - `limit`: Maximum number of data points per team (default: 1000, max: 10000)

    **Returns:**
    ```json
    {
        "days": 7,
        "teams": {
            "team1": {
                "history": [
                    {"timestamp": "2025-10-10T14:30:00+00:00", "value": 10500.25},
                    ...
                ],
                "data_points": 1000,
                "latest_value": 10750.50
            },
            ...
        }
    }
    ```
    """
    result: Dict[str, Any] = {"days": days, "teams": {}}

    for team_id in list_team_ids():
        history = read_portfolio_history(team_id, days=days, limit=limit)
        latest_value = history[-1]["value"] if history else None
        result["teams"][team_id] = {
            "history": history,
            "data_points": len(history),
            "latest_value": latest_value,
        }

    return result


@router.get("/api/v1/leaderboard/metrics")
def get_leaderboard_metrics(
    request: Request,
    days: Optional[int] = Query(
        None, description="Days to calculate metrics over (None = all data)", ge=1, le=365
    ),
):
    """Get performance metrics for all teams in a single response.

    Returns comprehensive performance metrics for each team, suitable for
    displaying in a dashboard or comparing team performance.

    **Parameters:**
    - `days`: Number of days to calculate metrics over (default: all available data)

    **Returns:**
    ```json
    {
        "generated_at": "2025-10-15T15:45:00+00:00",
        "days_analyzed": 30,
        "teams": {
            "team1": {
                "current_value": 10750.50,
                "total_return_percentage": 7.5,
                "sharpe_ratio": 1.85,
                "max_drawdown_percentage": -5.2,
                "data_points": 43200
            },
            ...
        },
        "rankings": {
            "by_return": ["team1", "team3", "team2"],
            "by_sharpe": ["team3", "team1", "team2"],
            "by_value": ["team1", "team2", "team3"]
        }
    }
    ```
    """
    from datetime import datetime, timezone

    teams_metrics: Dict[str, Any] = {}
    returns_list: List[tuple] = []
    sharpe_list: List[tuple] = []
    value_list: List[tuple] = []

    for team_id in list_team_ids():
        history = read_portfolio_history(team_id, days=days)
        if not history:
            teams_metrics[team_id] = {"error": "No data available"}
            continue

        metrics = calculate_performance_metrics(history)
        if "error" in metrics:
            teams_metrics[team_id] = metrics
            continue

        teams_metrics[team_id] = {
            "current_value": metrics.get("current_value"),
            "starting_value": metrics.get("starting_value"),
            "total_return_percentage": metrics.get("total_return_percentage"),
            "annualized_return_percentage": metrics.get("annualized_return_percentage"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "sortino_ratio": metrics.get("sortino_ratio"),
            "max_drawdown_percentage": metrics.get("max_drawdown_percentage"),
            "current_drawdown_percentage": metrics.get("current_drawdown_percentage"),
            "annualized_volatility_percentage": metrics.get(
                "annualized_volatility_percentage"
            ),
            "winning_trades": metrics.get("winning_trades"),
            "losing_trades": metrics.get("losing_trades"),
            "data_points": metrics.get("period", {}).get("data_points", 0),
            "period": metrics.get("period"),
        }

        # Collect for rankings
        total_return = metrics.get("total_return_percentage")
        sharpe = metrics.get("sharpe_ratio")
        current_value = metrics.get("current_value")

        if total_return is not None:
            returns_list.append((team_id, total_return))
        if sharpe is not None:
            sharpe_list.append((team_id, sharpe))
        if current_value is not None:
            value_list.append((team_id, current_value))

    # Sort rankings
    returns_list.sort(key=lambda x: x[1], reverse=True)
    sharpe_list.sort(key=lambda x: x[1], reverse=True)
    value_list.sort(key=lambda x: x[1], reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_analyzed": days,
        "teams": teams_metrics,
        "rankings": {
            "by_return": [t[0] for t in returns_list],
            "by_sharpe": [t[0] for t in sharpe_list],
            "by_value": [t[0] for t in value_list],
        },
    }
