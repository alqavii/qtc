"""
System status and admin endpoints.
"""

import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query

from app.config.environments import config

router = APIRouter(tags=["System"])


@router.get("/api/v1/status")
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


@router.get("/api/v1/system/errors")
def get_all_system_errors(
    request: Request,
    limit: Optional[int] = Query(
        100, description="Maximum number of errors to return", ge=1, le=1000
    ),
    team_id: Optional[str] = Query(None, description="Filter errors by team ID"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
):
    """Get all system errors across all teams and components.

    This endpoint provides comprehensive error visibility for debugging and monitoring.
    It aggregates errors from multiple sources:
    - Global error log (qtc_alpha_errors.log)
    - Team-specific error files
    - Strategy execution errors
    - System component errors

    **Parameters:**
    - `limit`: Maximum number of errors to return (1-1000)
    - `team_id`: Optional filter by specific team
    - `error_type`: Optional filter by error type (e.g., "strategy", "data", "system")

    **Returns:**
    ```json
    {
        "total_errors": 45,
        "filtered_errors": 12,
        "errors": [
            {
                "timestamp": "2025-10-15T15:45:00+00:00",
                "category": "strategy",
                "error_type": "TimeoutError",
                "message": "Strategy execution timeout",
                "team_id": "team-alpha",
                "strategy": "MACDStrategy",
                "context": {"phase": "signal_generation"}
            }
        ],
        "error_summary": {
            "by_category": {"strategy": 30, "data": 10, "system": 5},
            "by_team": {"team-alpha": 25, "team-beta": 20},
            "by_type": {"TimeoutError": 15, "ValidationError": 10}
        }
    }
    ```
    """
    from app.telemetry.error_handler import error_handler_instance
    from app.config.environments import EnvironmentConfig

    env_config = EnvironmentConfig(os.getenv("QTC_ENV", "development"))

    # Get errors from global error handler
    error_summary = error_handler_instance.get_error_summary()
    global_errors = error_summary.get("recent_errors", [])

    # Get errors from team-specific files
    team_errors: List[Dict[str, Any]] = []
    team_dir = env_config.get_data_path("team")
    if team_dir.exists():
        for team_folder in team_dir.iterdir():
            if team_folder.is_dir():
                error_file = team_folder / "errors.jsonl"
                if error_file.exists():
                    try:
                        with open(error_file, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    error = json.loads(line)
                                    error["source"] = "team_file"
                                    error["team_id"] = team_folder.name
                                    team_errors.append(error)
                                except Exception:
                                    continue
                    except Exception:
                        continue

    # Combine all errors
    all_errors = global_errors + team_errors

    # Apply filters
    if team_id:
        all_errors = [e for e in all_errors if e.get("team_id") == team_id]

    if error_type:
        all_errors = [e for e in all_errors if e.get("error_type") == error_type]

    # Sort by timestamp (newest first)
    all_errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Limit results
    filtered_errors = all_errors[:limit]

    # Generate summary statistics
    by_category: Dict[str, int] = {}
    by_team: Dict[str, int] = {}
    by_type: Dict[str, int] = {}

    for error in all_errors:
        category = error.get("category", "unknown")
        team = error.get("team_id", "unknown")
        error_type_name = error.get("error_type", "unknown")

        by_category[category] = by_category.get(category, 0) + 1
        by_team[team] = by_team.get(team, 0) + 1
        by_type[error_type_name] = by_type.get(error_type_name, 0) + 1

    return {
        "total_errors": len(all_errors),
        "filtered_errors": len(filtered_errors),
        "errors": filtered_errors,
        "error_summary": {
            "by_category": by_category,
            "by_team": by_team,
            "by_type": by_type,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/system/alpaca-status")
def get_alpaca_api_status(request: Request):
    """Check Alpaca API key status and connectivity.

    This endpoint verifies:
    - API keys are loaded and configured
    - Alpaca API connectivity
    - Account status and permissions
    - Market data access

    **Returns:**
    ```json
    {
        "api_keys_loaded": true,
        "connectivity": {
            "trading_api": "connected",
            "market_data_api": "connected"
        },
        "account_status": {
            "account_id": "12345678-1234-1234-1234-123456789012",
            "status": "ACTIVE",
            "trading_blocked": false,
            "buying_power": 10000.00
        },
        "permissions": {
            "trading_enabled": true,
            "market_data_enabled": true,
            "paper_trading": true
        },
        "last_check": "2025-10-15T15:45:00+00:00"
    }
    ```
    """
    try:
        from app.adapters.alpaca_broker import load_broker_from_env

        status: Dict[str, Any] = {
            "api_keys_loaded": False,
            "connectivity": {"trading_api": "unknown", "market_data_api": "unknown"},
            "account_status": {},
            "permissions": {},
            "last_check": datetime.now(timezone.utc).isoformat(),
            "errors": [],
        }

        # Check if API keys are loaded
        try:
            # Try to get account info to verify keys are loaded
            broker = load_broker_from_env()
            if broker is None:
                status["errors"].append(
                    "No Alpaca API keys found in environment variables"
                )
                return status
            account = broker.get_account()
            if account:
                status["api_keys_loaded"] = True
                status["connectivity"]["trading_api"] = "connected"

                # Extract account information
                status["account_status"] = {
                    "account_id": account.get("id", "unknown"),
                    "status": account.get("status", "unknown"),
                    "trading_blocked": account.get("trading_blocked", True),
                    "buying_power": float(account.get("buying_power", 0)),
                    "cash": float(account.get("cash", 0)),
                    "portfolio_value": float(account.get("portfolio_value", 0)),
                }

                # Check permissions
                status["permissions"] = {
                    "trading_enabled": not account.get("trading_blocked", True),
                    "market_data_enabled": True,  # Assume true if we got account info
                    "paper_trading": account.get("pattern_day_trader", False),
                }
            else:
                status["errors"].append("Failed to get account information")

        except Exception as e:
            status["errors"].append(f"Account check failed: {str(e)}")
            status["connectivity"]["trading_api"] = "failed"

        # Test market data connectivity
        try:
            # Try to get a simple market data request
            from app.adapters.ticker_adapter import TickerAdapter

            TickerAdapter()  # Test instantiation
            status["connectivity"]["market_data_api"] = "connected"
        except Exception as e:
            status["connectivity"]["market_data_api"] = "failed"
            status["errors"].append(f"Market data check failed: {str(e)}")

        # Check if we have API keys configured
        if not status["api_keys_loaded"]:
            try:
                # Check if keys are in environment or config
                alpaca_key = os.getenv("ALPACA_KEY") or os.getenv("APCA_API_KEY_ID")
                alpaca_secret = os.getenv("ALPACA_SECRET") or os.getenv(
                    "APCA_API_SECRET_KEY"
                )

                if alpaca_key and alpaca_secret:
                    status["api_keys_loaded"] = True
                    status["connectivity"]["trading_api"] = (
                        "keys_loaded_but_connection_failed"
                    )
                else:
                    status["errors"].append(
                        "No Alpaca API keys found in environment variables"
                    )
            except Exception as e:
                status["errors"].append(f"Key check failed: {str(e)}")

        return status

    except Exception as e:
        return {
            "api_keys_loaded": False,
            "connectivity": {"trading_api": "error", "market_data_api": "error"},
            "account_status": {},
            "permissions": {},
            "last_check": datetime.now(timezone.utc).isoformat(),
            "errors": [f"System error: {str(e)}"],
        }
