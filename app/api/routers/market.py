"""
Market data endpoints.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query, HTTPException

from app.services.auth import auth_manager

router = APIRouter(prefix="/api/v1/market", tags=["Market"])


@router.get("/bars")
def get_market_historical_bars(
    request: Request,
    symbols: str = Query(
        ...,
        description="Symbol or comma-separated symbols (e.g., 'AAPL' or 'AAPL,SPY,NVDA')",
    ),
    start: str = Query(
        ..., description="Start datetime (ISO 8601: 2025-10-01T09:30:00)"
    ),
    end: str = Query(..., description="End datetime (ISO 8601: 2025-10-10T16:00:00)"),
    key: str = Query(..., description="Team API key for authentication"),
):
    """Get historical minute bar data (OHLCV) for one or more symbols.

    This endpoint provides access to stored historical market data from the Parquet database.
    Supports both single symbol and multi-symbol queries in one unified interface.

    **Authentication:** Requires team API key

    **Parameters:**
    - `symbols`: Single symbol or comma-separated list (max 20 symbols)
    - `start`: Start datetime in ISO 8601 format
    - `end`: End datetime in ISO 8601 format
    - `key`: Team API key

    **Single Symbol Example:**
    ```
    GET /api/v1/market/bars?symbols=AAPL&start=2025-10-01T09:30:00&end=2025-10-02T16:00:00&key=YOUR_KEY
    ```

    **Multi-Symbol Example:**
    ```
    GET /api/v1/market/bars?symbols=AAPL,SPY,NVDA&start=2025-10-15T09:30:00&end=2025-10-16T16:00:00&key=YOUR_KEY
    ```
    """
    from app.services.data_api import StrategyDataAPI

    # Validate API key
    team_id = auth_manager.findTeamByKey(key)
    if not team_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="No symbols provided")

    if len(symbol_list) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 symbols per request")

    # Parse datetimes
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid datetime format. Use ISO 8601: YYYY-MM-DDTHH:MM:SS",
        )

    # Validate date range
    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end must be after start")

    if (end_dt - start_dt).days > 30:
        raise HTTPException(
            status_code=400, detail="Maximum range is 30 days per request"
        )

    # Validate symbols are in universe
    from app.config.settings import TICKER_UNIVERSE

    invalid_symbols = [s for s in symbol_list if s not in TICKER_UNIVERSE]
    if invalid_symbols:
        raise HTTPException(
            status_code=404,
            detail=f"Symbols not in ticker universe: {', '.join(invalid_symbols)}",
        )

    # Fetch data
    api = StrategyDataAPI()

    try:
        # Handle single vs multiple symbols
        if len(symbol_list) == 1:
            # Single symbol - return simple format
            symbol = symbol_list[0]
            df = api.getRange(symbol, start_dt, end_dt)

            if df.empty:
                return {
                    "symbol": symbol,
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                    "bar_count": 0,
                    "bars": [],
                    "message": "No data available for this time range",
                }

            # Limit to 10,000 bars
            if len(df) > 10000:
                step = max(1, len(df) // 10000)
                df = df.iloc[::step].head(10000)

            # Convert to response format
            bars = []
            for _, row in df.iterrows():
                bar_data = {
                    "timestamp": row["timestamp"].isoformat()
                    if hasattr(row["timestamp"], "isoformat")
                    else str(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
                if "volume" in row and row["volume"] is not None:
                    bar_data["volume"] = int(row["volume"])
                bars.append(bar_data)

            return {
                "symbol": symbol,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "bar_count": len(bars),
                "bars": bars,
            }

        else:
            # Multiple symbols - return dict format
            dfs = api.getRange(symbol_list, start_dt, end_dt)

            result = {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "symbols": symbol_list,
                "data": {},
            }

            for symbol in symbol_list:
                df = dfs.get(symbol)

                if df is None or df.empty:
                    result["data"][symbol] = {"bar_count": 0, "bars": []}
                    continue

                # Limit bars per symbol
                if len(df) > 10000:
                    step = max(1, len(df) // 10000)
                    df = df.iloc[::step].head(10000)

                bars = []
                for _, row in df.iterrows():
                    bar_data = {
                        "timestamp": row["timestamp"].isoformat()
                        if hasattr(row["timestamp"], "isoformat")
                        else str(row["timestamp"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    }
                    if "volume" in row and row["volume"] is not None:
                        bar_data["volume"] = int(row["volume"])
                    bars.append(bar_data)

                result["data"][symbol] = {"bar_count": len(bars), "bars": bars}

            return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")
