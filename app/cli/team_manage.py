from __future__ import annotations
import argparse
import json
import os
import shutil
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config.environments import EnvironmentConfig
from app.services.auth import auth_manager
from app.telemetry.activity import subscribe_activity


ROOT = Path(__file__).parents[2]
DATA_DIR = ROOT / "data"
TEAM_ROOT = DATA_DIR / "team"
REGISTRY = ROOT / "team_registry.yaml"
STRAT_ROOT = ROOT / "external_strategies"


def _slugify(name: str) -> str:
    s = name.strip().lower()
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug or "team"


def _load_registry() -> Dict[str, Any]:
    import yaml

    data: Dict[str, Any] = {}
    if REGISTRY.exists():
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    teams = data.get("teams")
    if not isinstance(teams, list):
        teams = []
    data["teams"] = teams
    return data


def _save_registry(reg: Dict[str, Any]) -> None:
    import yaml

    REGISTRY.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def _sync_strategy_file(team_id: str, source: Path) -> Path:
    """Copy strategy.py from source into external_strategies/<team_id>."""
    from shutil import copy2

    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Strategy source {source} not found")

    STRAT_ROOT.mkdir(parents=True, exist_ok=True)
    dest = STRAT_ROOT / team_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if source.is_file():
        candidate = source if source.name == "strategy.py" else None
    else:
        candidate = (
            (source / "strategy.py") if (source / "strategy.py").exists() else None
        )
        if candidate is None:
            matches = list(source.rglob("strategy.py"))
            candidate = matches[0] if matches else None

    if candidate is None:
        raise FileNotFoundError(f"strategy.py not found in {source}")

    copy2(candidate, dest / "strategy.py")
    return dest


def _update_registry_repo_dir(team_id: str, repo_dir: Path) -> None:
    reg = _load_registry()
    teams = reg.setdefault("teams", [])
    for entry in teams:
        if entry.get("team_id") == team_id:
            entry["repo_dir"] = str(repo_dir)
            break
    else:
        teams.append(
            {
                "team_id": team_id,
                "repo_dir": str(repo_dir),
                "entry_point": "strategy:Strategy",
                "initial_cash": 10000,
                "run_24_7": False,
            }
        )
    reg["teams"] = teams
    _save_registry(reg)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return Decimal("0")
        try:
            return Decimal(stripped)
        except InvalidOperation:
            return Decimal("0")
    if isinstance(value, dict):
        for key in ("__root__", "value", "amount"):
            if key in value:
                try:
                    return _to_decimal(value[key])
                except Exception:
                    continue
    return Decimal("0")


def _tail_jsonl(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not path or not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size <= 0:
                return None
            read = min(16384, size)
            f.seek(size - read)
            chunk = f.read().decode("utf-8", errors="ignore")
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except Exception:
                continue
    except Exception:
        return None
    return None


def view_teams() -> None:
    # List teams from data folder and show keys if present
    teams: List[str] = []
    if TEAM_ROOT.exists():
        teams = [p.name for p in TEAM_ROOT.iterdir() if p.is_dir()]
    # Load keys map
    try:
        key_map: Dict[str, str] = json.loads(
            (DATA_DIR / "api_keys.json").read_text(encoding="utf-8")
        )
    except Exception:
        key_map = {}
    if not teams and not key_map:
        print("No teams found.")
        return
    for tid in sorted(set(list(teams) + list(key_map.keys()))):
        key = key_map.get(tid, "<no key>")
        print(f"{tid}: {key}")


def add_team(
    name: str,
    initial_cash: Decimal = Decimal(10000),
    *,
    repo_path: str | None = None,
    run_24_7: bool = False,
) -> None:
    team_id = _slugify(name)
    initial_cash = Decimal(initial_cash)
    # Ensure data dirs
    (TEAM_ROOT / team_id / "portfolio").mkdir(parents=True, exist_ok=True)
    (TEAM_ROOT / team_id).mkdir(parents=True, exist_ok=True)
    # Ensure API key
    key = auth_manager.generateKey(team_id)
    auth_manager._maybe_reload()
    # Update registry: prefer Git URL by default; fall back to local path if provided
    reg = _load_registry()
    teams = reg.setdefault("teams", [])
    # Remove any existing entry with same id
    teams = [t for t in teams if t.get("team_id") != team_id]
    reg["teams"] = teams
    entry: Dict[str, Any] = {
        "team_id": team_id,
        "entry_point": "strategy:Strategy",
        "initial_cash": float(initial_cash),
        "run_24_7": bool(run_24_7),
    }
    if repo_path:
        try:
            dest = _sync_strategy_file(team_id, Path(repo_path).resolve())
            entry["repo_dir"] = str(dest)
        except Exception as exc:
            print(f"Warning: unable to sync local strategy for '{team_id}': {exc}")
    else:
        # No Git URL - strategies must be uploaded via web interface
        print(f"Team '{team_id}' created. Upload strategy via web interface.")
    teams.append(entry)
    reg["teams"] = teams
    _save_registry(reg)

    add_money(name, Decimal(initial_cash))
    print(f"Added team '{name}' as '{team_id}'. Key: {key}")


def remove_team(name_or_id: str, *, purge_data: bool = True) -> None:
    team_id = _slugify(name_or_id)
    # Remove data dir
    if purge_data and (TEAM_ROOT / team_id).exists():
        shutil.rmtree(TEAM_ROOT / team_id)
    # Remove key
    try:
        key_file = DATA_DIR / "api_keys.json"
        keys = (
            json.loads(key_file.read_text(encoding="utf-8"))
            if key_file.exists()
            else {}
        )
        if team_id in keys:
            del keys[team_id]
            key_file.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    except Exception:
        pass
    # Remove from registry
    reg = _load_registry()
    teams = reg.get("teams", [])
    teams = [t for t in teams if t.get("team_id") != team_id]
    reg["teams"] = teams
    _save_registry(reg)
    # Remove strategy working directory
    try:
        strat_dir = STRAT_ROOT / team_id
        if strat_dir.exists():
            shutil.rmtree(strat_dir)
    except Exception:
        pass
    print(f"Removed team '{team_id}'.")


def add_money(name_or_id: str, amount: Decimal) -> None:
    team_id = _slugify(name_or_id)
    portfolio_dir = TEAM_ROOT / team_id / "portfolio"
    had_history = portfolio_dir.exists()
    portfolio_dir.mkdir(parents=True, exist_ok=True)

    json_files = (
        sorted([p for p in portfolio_dir.glob("*.jsonl") if p.is_file()])
        if had_history
        else []
    )
    last_file: Optional[Path] = json_files[-1] if json_files else None
    last_snapshot = _tail_jsonl(last_file) if last_file else None
    if last_snapshot is None:
        last_snapshot = {
            "team_id": team_id,
            "cash": 0,
            "market_value": 0,
            "positions": {},
        }
    else:
        last_snapshot = dict(last_snapshot)

    positions_value = Decimal("0")
    positions = last_snapshot.get("positions", {})
    if isinstance(positions, dict):
        for info in positions.values():
            if isinstance(info, dict):
                positions_value += _to_decimal(info.get("value"))

    base_cash = _to_decimal(last_snapshot.get("cash"))
    base_market = _to_decimal(last_snapshot.get("market_value"))
    if base_market == Decimal("0"):
        base_market = _to_decimal(last_snapshot.get("portfolio_value"))
    if base_market == Decimal("0"):
        base_market = base_cash + positions_value

    now = datetime.now(timezone.utc).replace(microsecond=0)
    new_cash = base_cash + amount
    new_market_value = base_market + amount

    new_snapshot = dict(last_snapshot)
    new_snapshot["team_id"] = team_id
    new_snapshot["timestamp"] = now.isoformat()
    new_snapshot["cash"] = float(new_cash)
    new_snapshot["market_value"] = float(new_market_value)
    # Do not annotate adjustments; act like a direct portfolio update

    today_file = portfolio_dir / f"{now.date().isoformat()}.jsonl"
    portfolio_dir.mkdir(parents=True, exist_ok=True)
    with open(today_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(new_snapshot, default=str) + "\n")

    print(
        f"Credited ${float(amount):,.2f} to team '{team_id}'. Snapshot appended to {today_file}."
    )
    if last_file and last_file != today_file:
        print(f"Previous snapshot source: {last_file}")


def _manual_trade(
    name_or_id: str,
    symbol: str,
    quantity: Decimal,
    *,
    side: str = "buy",
    price: float | None = None,
) -> None:
    """Place a manual buy/sell for a team, identical to a strategy-driven trade.

    - Sends order to Alpaca when broker credentials are configured.
    - Updates local portfolio state and saves trade + snapshot to disk.
    """
    from decimal import Decimal as D
    from app.models.teams import Team, Strategy as StratModel, Portfolio, Position
    from app.models.trading import TradeRequest
    from app.services.trade_executor import trade_executor
    from app.adapters.ticker_adapter import TickerAdapter

    team_id = _slugify(name_or_id)

    # Load last snapshot to reconstruct a Team object
    portfolio_dir = TEAM_ROOT / team_id / "portfolio"
    last_file = None
    if portfolio_dir.exists():
        files = sorted([p for p in portfolio_dir.glob("*.jsonl") if p.is_file()])
        last_file = files[-1] if files else None
    last = _tail_jsonl(last_file)

    cash = D("0")
    positions: Dict[str, Position] = {}
    if isinstance(last, dict):
        try:
            cash = D(str(last.get("cash", "0")))
        except Exception:
            cash = D("0")
        pos = last.get("positions") or {}
        if isinstance(pos, dict):
            for sym, info in pos.items():
                try:
                    positions[sym] = Position(
                        symbol=sym,
                        quantity=D(str(info.get("quantity", "0"))),
                        side=str(info.get("side", "buy")),  # type: ignore
                        avgCost=D(str(info.get("avg_cost", info.get("avgCost", "0")))),
                        costBasis=D("0"),
                    )
                except Exception:
                    continue

    team = Team(
        name=team_id,
        strategy=StratModel(name="manual", repoPath=None, entryPoint=None, params={}),
        portfolio=Portfolio(base="USD", freeCash=cash, positions=positions),
    )

    sym = symbol.upper()
    px: D
    if price is not None:
        px = D(str(price))
    else:
        bars = TickerAdapter.fetchBasic([sym])
        found = None
        for b in bars:
            if b.ticker.upper() == sym:
                found = b
                break
        if not found:
            print(f"Failed to resolve live price for {sym}; provide --price")
            return
        px = D(str(found.close))

    req = TradeRequest(
        team_id=team_id,
        symbol=sym,
        side="buy" if side == "buy" else "sell",
        quantity=D(str(quantity)),
        price=px,
        order_type="market",
    )

    ok, msg = trade_executor.execute(team, req, current_prices={sym: px})
    print(msg)


# Removed pullstrat function - strategies now uploaded via web interface


def view_all_errors(
    limit: int = 50, team_id: str | None = None, error_type: str | None = None
) -> None:
    """Display all system errors across all teams and components."""
    from app.telemetry.error_handler import error_handler_instance
    from app.config.environments import EnvironmentConfig

    config = EnvironmentConfig(os.getenv("QTC_ENV", "development"))

    print("=== System Error Report ===")
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()

    # Get errors from global error handler
    error_summary = error_handler_instance.get_error_summary()
    global_errors = error_summary.get("recent_errors", [])

    # Get errors from team-specific files
    team_errors = []
    team_dir = config.get_data_path("team")
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
        print(f"Filtered by team: {team_id}")

    if error_type:
        all_errors = [e for e in all_errors if e.get("error_type") == error_type]
        print(f"Filtered by error type: {error_type}")

    # Sort by timestamp (newest first)
    all_errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Limit results
    filtered_errors = all_errors[:limit]

    print(f"Total errors found: {len(all_errors)}")
    print(f"Showing: {len(filtered_errors)}")
    print()

    if not filtered_errors:
        print("No errors found.")
        return

    # Generate summary statistics
    by_category = {}
    by_team = {}
    by_type = {}

    for error in all_errors:
        category = error.get("category", "unknown")
        team = error.get("team_id", "unknown")
        error_type_name = error.get("error_type", "unknown")

        by_category[category] = by_category.get(category, 0) + 1
        by_team[team] = by_team.get(team, 0) + 1
        by_type[error_type_name] = by_type.get(error_type_name, 0) + 1

    # Print summary
    print("=== Error Summary ===")
    print("By Category:")
    for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count}")

    print("\nBy Team:")
    for team, count in sorted(by_team.items(), key=lambda x: x[1], reverse=True):
        print(f"  {team}: {count}")

    print("\nBy Error Type:")
    for err_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
        print(f"  {err_type}: {count}")

    print("\n=== Recent Errors ===")
    for i, error in enumerate(filtered_errors, 1):
        timestamp = error.get("timestamp", "unknown")
        category = error.get("category", "unknown")
        error_type_name = error.get("error_type", "unknown")
        message = error.get("message", "No message")
        team_id = error.get("team_id", "unknown")

        print(f"{i:3d}. [{timestamp}] {category.upper()} - {error_type_name}")
        print(f"     Team: {team_id}")
        print(f"     Message: {message}")

        # Show context if available
        context = error.get("context", {})
        if context:
            context_str = ", ".join(f"{k}={v}" for k, v in context.items())
            print(f"     Context: {context_str}")

        print()


def backfill_data(period: str) -> None:
    """Backfill historical price data for all tickers in TICKER_UNIVERSE.

    Args:
        period: Time period to backfill ('1y', '2y', '3y', 'start' for Jan 1, 2020)
    """
    from datetime import date, timedelta
    from app.adapters.ticker_adapter import TickerAdapter
    from app.adapters.parquet_writer import ParquetWriter
    from app.config.settings import TICKER_UNIVERSE
    from app.services.market_hours import us_equity_market_open
    import time

    print("=" * 70)
    print("  HISTORICAL DATA BACKFILL")
    print("=" * 70)

    # Check if credentials are loaded (should be available from systemctl service)
    import os

    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")

    if not api_key or not api_secret:
        print("WARNING: Alpaca API credentials not found!")
        print(
            "Make sure the orchestrator service is running or environment variables are set."
        )
        print("Get credentials from: https://app.alpaca.markets/")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Aborted by user")
            return

    # Check if we're in market hours
    if us_equity_market_open():
        print("WARNING: Market is currently open!")
        print(
            "Backfilling during market hours may interfere with live data collection."
        )
        response = input("Continue anyway? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Aborted by user")
            return
    else:
        print("Market is closed - safe to proceed with backfill")

    # Calculate date range
    end_date = date.today()
    if period == "start":
        start_date = date(2020, 1, 1)
        period_desc = "from Jan 1, 2020"
    elif period == "1y":
        start_date = end_date - timedelta(days=365)
        period_desc = "1 year"
    elif period == "2y":
        start_date = end_date - timedelta(days=2 * 365)
        period_desc = "2 years"
    elif period == "3y":
        start_date = end_date - timedelta(days=3 * 365)
        period_desc = "3 years"
    else:
        print(f"ERROR Invalid period: {period}. Use: 1y, 2y, 3y, or start")
        return

    print(f"\nTicker Universe: {len(TICKER_UNIVERSE)} tickers")
    print(f"Period: {period_desc} ({start_date} to {end_date})")

    # Count potential trading days
    potential_days = 0
    check_date = start_date
    while check_date <= end_date:
        if check_date.weekday() < 5:  # Skip weekends
            potential_days += 1
        check_date += timedelta(days=1)

    print(f"Potential trading days: ~{potential_days} days")

    # Estimate time and storage
    batches_per_day = (
        len(TICKER_UNIVERSE) + TickerAdapter.BATCH_SIZE - 1
    ) // TickerAdapter.BATCH_SIZE
    estimated_api_calls = potential_days * batches_per_day
    estimated_time_minutes = estimated_api_calls / 150  # Conservative rate
    estimated_storage_gb = (
        (potential_days * len(TICKER_UNIVERSE) * 390) / (1024**3) * 0.1
    )  # Rough estimate

    print("\nEstimates:")
    print(f"   API calls: ~{estimated_api_calls:,}")
    print(f"   Time: ~{estimated_time_minutes:.1f} minutes")
    print(f"   Storage: ~{estimated_storage_gb:.1f} GB")

    # Confirm before proceeding
    print("\n" + "=" * 70)
    response = input("Ready to start backfill? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        print("Aborted by user")
        return

    print("\nStarting backfill...\n")

    # Track progress
    current_date = start_date
    days_completed = 0
    days_with_data = 0
    total_bars = 0
    errors = 0
    start_time = time.time()

    while current_date <= end_date:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        try:
            elapsed = time.time() - start_time
            rate = days_completed / elapsed if elapsed > 0 else 0
            eta_minutes = (
                (potential_days - days_completed) / (rate * 60) if rate > 0 else 0
            )

            print(
                f"[{days_completed + 1}/{potential_days}] {current_date} ",
                end="",
                flush=True,
            )
            print(f"(ETA: {eta_minutes:.1f}min) ... ", end="", flush=True)

            # Fetch data for this day
            bars = TickerAdapter.fetchHistoricalDay(current_date, TICKER_UNIVERSE)

            if bars:
                # Write to Parquet (overwrite mode - no duplication)
                ParquetWriter.writeDay(bars, root="data/prices/minute_bars")
                print(f"SUCCESS {len(bars):,} bars")
                days_with_data += 1
                total_bars += len(bars)
            else:
                print("WARNING No data (holiday/non-trading day)")

            days_completed += 1

            # Rate limiting
            time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\nWARNING Interrupted by user")
            print(f"   Completed: {days_completed}/{potential_days} days")
            print("   Can resume by running again (will overwrite existing data)")
            return
        except Exception as e:
            print(f"ERROR Error: {e}")
            errors += 1
            if errors > 10:
                print(f"\nERROR Too many errors ({errors}), stopping")
                return

        current_date += timedelta(days=1)

    # Final summary
    elapsed_total = time.time() - start_time
    print("\nSUCCESS Backfill completed!")
    print(f"   Days processed: {days_completed}")
    print(f"   Days with data: {days_with_data}")
    print(f"   Total bars: {total_bars:,}")
    print(f"   Errors: {errors}")
    print(f"   Time elapsed: {elapsed_total / 60:.1f} minutes")
    print("\nData written to: data/prices/minute_bars/")


def check_alpaca_status() -> None:
    """Check Alpaca API key status and connectivity."""
    print("=== Alpaca API Status Check ===")
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()

    try:
        from app.adapters.alpaca_broker import load_broker_from_env

        # Check if API keys are loaded
        print("Checking API Keys...")
        try:
            # Try to get account info to verify keys are loaded
            broker = load_broker_from_env()
            if broker is None:
                print("ERROR API Keys: Not configured")
                return
            account = broker.get_account()
            if account:
                print("OK API Keys: Loaded and working")
                print("OK Trading API: Connected")

                # Extract account information
                account_id = account.get("id", "unknown")
                status = account.get("status", "unknown")
                trading_blocked = account.get("trading_blocked", True)
                buying_power = float(account.get("buying_power", 0))
                cash = float(account.get("cash", 0))
                portfolio_value = float(account.get("portfolio_value", 0))

                print("\nAccount Information:")
                print(f"   Account ID: {account_id}")
                print(f"   Status: {status}")
                print(f"   Trading Blocked: {'Yes' if trading_blocked else 'No'}")
                print(f"   Buying Power: ${buying_power:,.2f}")
                print(f"   Cash: ${cash:,.2f}")
                print(f"   Portfolio Value: ${portfolio_value:,.2f}")

                # Check permissions
                trading_enabled = not trading_blocked
                print("\nPermissions:")
                print(f"   Trading Enabled: {'Yes' if trading_enabled else 'No'}")
                print("   Market Data: Yes")
                print(
                    f"   Paper Trading: {'Yes' if account.get('pattern_day_trader', False) else 'No'}"
                )

            else:
                print("ERROR API Keys: Failed to get account information")

        except Exception as e:
            print(f"ERROR Trading API: Failed - {str(e)}")

        # Test market data connectivity
        print("\nChecking Market Data...")
        try:
            from app.adapters.ticker_adapter import TickerAdapter

            TickerAdapter()
            print("OK Market Data API: Connected")
        except Exception as e:
            print(f"ERROR Market Data API: Failed - {str(e)}")

        # Check environment variables
        print("\nEnvironment Variables:")
        import os

        alpaca_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv(
            "APCA_API_SECRET_KEY"
        )

        if alpaca_key:
            print(f"   ALPACA_API_KEY: {'*' * 8}{alpaca_key[-4:]}")
        else:
            print("   ALPACA_API_KEY: Not set")

        if alpaca_secret:
            print(f"   ALPACA_SECRET_KEY: {'*' * 8}{alpaca_secret[-4:]}")
        else:
            print("   ALPACA_SECRET_KEY: Not set")

    except Exception as e:
        print(f"ERROR System Error: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Check if Alpaca API keys are set in environment variables")
        print("2. Verify the keys are valid and have proper permissions")
        print("3. Check network connectivity to Alpaca servers")
        print("4. Ensure you're using the correct environment (paper vs live)")


def check_status(*, show_positions: bool = False) -> None:
    """Display the runtime status emitted by the orchestrator."""
    cfg = EnvironmentConfig(os.getenv("QTC_ENV", "development"))
    status_path = cfg.get_data_path("runtime/status.json")
    if not status_path.exists():
        print("Runtime status not found. Start the trading engine to populate it.")
        reg = _load_registry()
        teams = [
            entry.get("team_id")
            for entry in reg.get("teams", [])
            if entry.get("team_id")
        ]
        if teams:
            print("Registered teams:")
            for tid in teams:
                print(f"  - {tid}")
        return

    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read runtime status: {exc}")
        return

    teams = data.get("teams") or []
    print(f"Last heartbeat: {data.get('timestamp', 'unknown')}")
    if "running" in data:
        print(f"Engine running: {bool(data.get('running'))}")
    symbols = sorted(data.get("symbols") or [])
    if symbols:
        print(f"Latest symbols: {', '.join(symbols)}")
    bar_count = data.get("bar_count")
    if bar_count is not None:
        print(f"Bars processed: {bar_count}")

    if not teams:
        print("No team activity recorded yet.")
        return

    header = f"{'Team':<16}{'Active':<8}{'Last Snapshot':<22}{'Market Value':<18}{'Last Trade'}"
    print(header)
    print("-" * len(header))

    for entry in teams:
        team_id = entry.get("team_id", "?")
        active = "yes" if entry.get("active") else "no"
        last_snapshot = entry.get("last_snapshot", "n/a")
        market_value = _format_money(entry.get("market_value"))
        last_trade = entry.get("last_trade")
        if isinstance(last_trade, dict):
            lt_piece = f"{last_trade.get('timestamp', 'n/a')} {last_trade.get('side', '?')} {last_trade.get('symbol', '')}".strip()
        else:
            lt_piece = "n/a"
        print(
            f"{team_id:<16}{active:<8}{last_snapshot:<22}{market_value:<18}{lt_piece}"
        )
        if entry.get("error"):
            print(f"    warning: {entry['error']}")
        if show_positions:
            for pos in entry.get("positions") or []:
                sym = pos.get("symbol", "?")
                qty = pos.get("quantity", 0)
                side = pos.get("side", "?")
                value = _format_money(pos.get("value"))
                print(f"    {sym}: {qty} {side} ({value})")

    global_info = data.get("global")
    if isinstance(global_info, dict):
        print("\nGlobal portfolio:")
        print(f"  Timestamp: {global_info.get('timestamp', 'n/a')}")
        print(f"  Source: {global_info.get('source', 'unknown')}")
        print(f"  Market Value: {_format_money(global_info.get('market_value'))}")
        print(f"  Cash: {_format_money(global_info.get('cash'))}")
        if show_positions:
            for pos in global_info.get("positions") or []:
                sym = pos.get("symbol", "?")
                qty = pos.get("quantity", 0)
                side = pos.get("side", "?")
                value = _format_money(pos.get("value"))
                print(f"    {sym}: {qty} {side} ({value})")


def main() -> None:
    p = argparse.ArgumentParser(description="Team management CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("viewteams", help="List teams and their keys")

    ap = sub.add_parser(
        "addteam", help="Add a new team (creates data/, key, registry entry)"
    )
    ap.add_argument("name", help="Team name, e.g. 'Team Blue'")
    ap.add_argument(
        "--repo",
        dest="repo_path",
        default=None,
        help="Local path to strategy folder (if not using Git)",
    )
    ap.add_argument(
        "--git",
        dest="repo_path",
        default=None,
        help="Git URL for the team's strategy (default: https://github.com/org/strategy.git)",
    )
    ap.add_argument("--cash", dest="initial_cash", type=int, default=10000)
    ap.add_argument(
        "--run-24-7",
        dest="run_24_7",
        action="store_true",
        help="Mark the team to run outside regular market hours",
    )

    rp = sub.add_parser("removeteam", help="Remove an existing team")
    rp.add_argument("name", help="Team name or id to remove")
    rp.add_argument(
        "--keep-data", action="store_true", help="Keep data/team/<id> directory"
    )

    mp = sub.add_parser("addmoney", help="Credit cash to a team for the latest tick")
    mp.add_argument("name", help="Team name or id")
    mp.add_argument("amount", type=Decimal, help="Amount (USD) to credit")

    # Manual trade commands (act as if team placed them)
    bp = sub.add_parser(
        "buy",
        help="Place a buy for team: buy <team> <symbol> <quantity> [--price]",
    )
    bp.add_argument("name", help="Team name or id")
    bp.add_argument("symbol", help="Ticker symbol (e.g., BTC, AAPL)")
    bp.add_argument("quantity", type=Decimal)
    bp.add_argument("--price", type=float, default=None)

    sp = sub.add_parser(
        "sell",
        help="Place a sell for team: sell <team> <symbol> <quantity> [--price]",
    )
    sp.add_argument("name", help="Team name or id")
    sp.add_argument("symbol", help="Ticker symbol (e.g., BTC, AAPL)")
    sp.add_argument("quantity", type=Decimal)
    sp.add_argument("--price", type=float, default=None)

    vt = sub.add_parser("viewtrade", help="Show the last trade made for a team")
    vt.add_argument("name", help="Team name or id")

    pp = sub.add_parser(
        "pullstrat", help="DEPRECATED: Strategies now uploaded via web interface"
    )
    pp.add_argument("name", help="Team name or id")
    pp.set_defaults(
        func=lambda args: print(
            "pullstrat command is deprecated. Use web interface to upload strategies."
        )
    )

    ar = sub.add_parser(
        "addrepo", help="DEPRECATED: Git repo management disabled - use web interface"
    )
    ar.add_argument("name", help="Team name or id")
    ar.add_argument("url", help="Git URL of the strategy repo")
    ar.add_argument("--branch", default="main")
    ar.set_defaults(
        func=lambda args: print(
            "addrepo command is deprecated. Use web interface to upload strategies."
        )
    )

    sub.add_parser("checkdaily", help="Run daily team sanity checks")

    # Live activity feed (terminal streaming)
    sub.add_parser("viewactivity", help="Stream live activity; Ctrl+C to stop")

    cs = sub.add_parser("checkstatus", help="Show live strategy runtime status")
    cs.add_argument(
        "--details",
        action="store_true",
        help="Include position-level details for each team",
    )

    # Error and debugging commands
    ve = sub.add_parser("viewerrors", help="View all system errors across teams")
    ve.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of errors to show (default: 50)",
    )
    ve.add_argument(
        "--team",
        help="Filter errors by specific team ID",
    )
    ve.add_argument(
        "--type",
        help="Filter errors by error type (e.g., TimeoutError, ValidationError)",
    )

    sub.add_parser("alpacastatus", help="Check Alpaca API key status and connectivity")

    # Backfill command
    bf = sub.add_parser(
        "backfill", help="Backfill historical price data for all tickers"
    )
    bf.add_argument(
        "period",
        choices=["1y", "2y", "3y", "start"],
        help="Time period to backfill (1y=1 year, 2y=2 years, 3y=3 years, start=Jan 1, 2020)",
    )

    args = p.parse_args()
    if args.cmd == "viewteams":
        view_teams()
    elif args.cmd == "addteam":
        add_team(
            args.name,
            repo_path=args.repo_path,
            initial_cash=args.initial_cash,
            run_24_7=args.run_24_7,
        )
    elif args.cmd == "removeteam":
        remove_team(args.name, purge_data=not args.keep_data)
    elif args.cmd == "viewtrade":
        # Tail data/team/<id>/trades.jsonl and print last line prettily
        tid = _slugify(args.name)
        path = TEAM_ROOT / tid / "trades.jsonl"
        if not path.exists():
            print(f"No trades found for team '{tid}'.")
            return
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                read = min(65536, size)
                f.seek(size - read)
                chunk = f.read().decode("utf-8", errors="ignore")
            lines = [ln for ln in chunk.splitlines() if ln.strip()]
            last = lines[-1]
            obj = json.loads(last)
            print(
                {
                    "timestamp": obj.get("timestamp"),
                    "symbol": obj.get("symbol"),
                    "side": obj.get("side"),
                    "quantity": obj.get("quantity"),
                    "price": obj.get("price"),
                    "status": obj.get("status") or obj.get("success"),
                    "message": obj.get("message"),
                    "broker_order_id": obj.get("broker_order_id"),
                }
            )
        except Exception as e:
            print(f"Failed to read last trade: {e}")
    elif args.cmd == "pullstrat":
        print(
            "pullstrat command is deprecated. Use web interface to upload strategies."
        )
    elif args.cmd == "addrepo":
        print("addrepo command is deprecated. Use web interface to upload strategies.")
    elif args.cmd == "addmoney":
        add_money(args.name, args.amount)

    elif args.cmd in ("buy", "sell"):
        _manual_trade(
            args.name, args.symbol, args.quantity, side=args.cmd, price=args.price
        )

    elif args.cmd == "viewactivity":
        try:
            from zoneinfo import ZoneInfo

            london = ZoneInfo("Europe/London")
            for entry in subscribe_activity(tail=200):
                ts_display = entry.timestamp.astimezone(london).strftime("%H:%M:%S")
                print(f"{ts_display} | {entry.message}")
        except KeyboardInterrupt:
            return

    elif args.cmd == "checkstatus":
        check_status(show_positions=args.details)

    elif args.cmd == "viewerrors":
        view_all_errors(limit=args.limit, team_id=args.team, error_type=args.type)

    elif args.cmd == "alpacastatus":
        check_alpaca_status()

    elif args.cmd == "backfill":
        backfill_data(args.period)


if __name__ == "__main__":
    main()
