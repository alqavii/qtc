import asyncio
import logging
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
import signal
import sys
import argparse
import json
import yaml
import os
from pathlib import Path

from app.adapters.ticker_adapter import TickerAdapter
from app.adapters.parquet_writer import ParquetWriter
from app.services.minute_service import MinuteService
from app.services.trade_executor import trade_executor
from app.services.caching import cache_manager
from app.models.teams import Team, Strategy, Portfolio
from app.loaders.strategy_loader import load_strategy_from_folder
from app.models.ticker_data import MinuteBar
from app.models.trading import StrategySignal, TradeRequest
from app.performance.performance_tracker import performance_tracker
from app.config.environments import EnvironmentConfig
from app.telemetry import error_handler_instance, configure_logging
from app.loaders.git_fetch import sync_all_from_registry
from app.services.data_api import StrategyDataAPI
from app.services.market_hours import us_equity_market_open
from app.core import slugify
import shutil
from app.cli.team_manage import (
    pullstrat as tm_pullstrat,
    _load_registry,
)  # adjust path if needed


logger = logging.getLogger(__name__)


class QTCAlphaOrchestrator:
    def _reconcile_teams_with_registry(self) -> None:
        """Drop any loaded teams that are no longer in team_registry.yaml.

        Keeps long-running orchestrators in sync with CLI removals without restart.
        """
        try:
            if not self._registry_path:
                return
            p = Path(self._registry_path)
            if not p.exists():
                return
            reg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            desired: set[str] = set()
            for t in reg.get("teams") or []:
                tid = t.get("team_id") or t.get("name") or ""
                if tid:
                    desired.add(slugify(tid))
            current = set(self.teams.keys())
            to_remove = current - desired
            for tid in list(to_remove):
                self.teams.pop(tid, None)
        except Exception:
            return

    """Main orchestrator for the QTC Alpha trading system"""

    def __init__(self) -> None:
        self.teams: Dict[str, Team] = {}
        self._loaded_strategies: Dict[str, Any] = {}
        self._data_api = StrategyDataAPI()
        self._lastPortfolioFoldDay: Optional[date] = None
        self._globalHistory: List[Dict[str, Any]] = []
        self._latest_prices: Dict[str, Decimal] = {}
        self._team_runtime_status: Dict[str, Dict[str, Any]] = {}
        runtime_cfg = EnvironmentConfig(os.getenv("QTC_ENV", "development"))
        self._status_path = runtime_cfg.get_data_path("runtime/status.json")
        self._status_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_global_snapshot: Optional[Dict[str, Any]] = None
        self.minute_service = MinuteService(
            fetch=TickerAdapter.fetchBasic,
            write=ParquetWriter.appendParquet,
            post_hook=self._process_market_data,
            historical_fetch_day=TickerAdapter.fetchHistoricalDay,
            write_day=ParquetWriter.writeDay,
        )
        self.running = False
        # Determine registry path: env override or default to repo root team_registry.yaml
        default_registry = Path(__file__).parents[1] / "team_registry.yaml"
        self._registry_path: Optional[str] = os.getenv("QTC_REGISTRY_PATH") or (
            str(default_registry) if default_registry.exists() else None
        )
        self._daily_sync_task: Optional[asyncio.Task[None]] = None
        self._order_reconciliation_task: Optional[asyncio.Task[None]] = None
        # Use shared performance tracker
        self.performance_tracker = performance_tracker

        # Initialize data repair service
        from app.services.data_repair_service import data_repair_service

        self.data_repair_service = data_repair_service

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Optional[object]) -> None:
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    def create_team(
        self,
        name: str,
        repo_path: str,
        entry_point: str,
        initial_cash: Decimal = Decimal("10000"),
        params: Optional[Dict[str, Any]] = None,
    ) -> Team:
        """Create a new trading team using a user-provided strategy module."""

        strategy = Strategy(
            name="custom",
            repoPath=repo_path,
            entryPoint=entry_point,
            params=params or {},
        )

        portfolio = Portfolio(base="USD", freeCash=initial_cash, positions={})

        team = Team(name=name, strategy=strategy, portfolio=portfolio)

        # Use the registry/team slug as the runtime team key
        self.teams[name] = team
        logger.info(
            f"Created team {name} with strategy {entry_point} at {repo_path} and ${initial_cash} initial capital"
        )

        return team

    async def _process_market_data(self, bars: List[MinuteBar]) -> None:
        """Process new market data and execute strategies"""
        bar_count = len(bars)
        logger.info("Processing %s new market data bars", bar_count)

        # Reconcile loaded teams with registry (supports live remove)
        self._reconcile_teams_with_registry()

        minute_mark = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        bars_by_symbol: Dict[str, List[MinuteBar]] = {}
        current_prices: Dict[str, Decimal] = {}
        bar_timestamps: List[datetime] = []

        for bar in bars:
            symbol = bar.ticker
            ts = bar.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            ts = ts.replace(second=0, microsecond=0)
            bar_timestamps.append(ts)
            bars_by_symbol.setdefault(symbol, []).append(bar)
            current_prices[symbol] = Decimal(str(bar.close))

        if bar_timestamps:
            # Use the most recent bar minute, not the oldest, to avoid "stuck" display
            minute_mark = max(bar_timestamps)

        if not bars:
            current_prices = dict(self._latest_prices)

        if bars_by_symbol:
            for symbol, symbol_bars in bars_by_symbol.items():
                cache_manager.cache_bars(symbol_bars, symbol)
                self._latest_prices[symbol] = current_prices[symbol]

        try:
            from app.telemetry import record_activity

            record_activity(
                f"received minutebars for {minute_mark.strftime('%H:%M')} ({bar_count} symbols)"
            )
        except Exception:
            pass

        market_open_now = us_equity_market_open()
        should_run_map: Dict[str, bool] = {}

        def _to_float(value: Any) -> Any:
            try:
                return float(value)
            except Exception:
                return value

        def _last_trade(team_id: str) -> Optional[Dict[str, Any]]:
            for rec in reversed(trade_executor.trade_history):
                if rec.get("team_id") == team_id:
                    ts = rec.get("timestamp")
                    if isinstance(ts, datetime):
                        ts_val = ts.isoformat()
                    else:
                        ts_val = str(ts)
                    return {
                        "timestamp": ts_val,
                        "symbol": rec.get("symbol"),
                        "side": rec.get("side"),
                        "quantity": _to_float(rec.get("quantity")),
                        "price": _to_float(rec.get("execution_price")),
                    }
            return None

        # Pre-trade snapshot for each team so every minute has one portfolio line
        for tid, team in self.teams.items():
            run_247 = bool(
                team.strategy.params.get("run_24_7", False)
                or os.getenv("QTC_RUN_24_7") == "1"
            )
            should_run = run_247 or market_open_now
            should_run_map[tid] = should_run
            status_entry: Dict[str, Any] = self._team_runtime_status.get(tid, {})
            status_entry.update(
                {
                    "team_id": tid,
                    "strategy": team.strategy.entryPoint or "strategy:Strategy",
                    "repo": team.strategy.repoPath,
                    "run_24_7": run_247,
                    "active": should_run,
                    "market_open": market_open_now,
                    "last_snapshot": minute_mark.isoformat(),
                }
            )
            try:
                performance_tracker.update_portfolio_snapshot(
                    team, current_prices, timestamp=minute_mark
                )
                snap = trade_executor.buildSnapshot(team, current_prices)
                snap.timestamp = minute_mark
                trade_executor.appendPortfolioSnapshot(snap)
                positions_summary = [
                    {
                        "symbol": sym,
                        "quantity": _to_float(pos.quantity),
                        "side": pos.side,
                        "value": _to_float(pos.value),
                    }
                    for sym, pos in snap.positions.items()
                ]
                status_entry.update(
                    {
                        "cash": _to_float(snap.cash),
                        "market_value": _to_float(snap.market_value),
                        "positions": positions_summary,
                        "positions_count": len(positions_summary),
                        "last_trade": _last_trade(tid),
                    }
                )
                status_entry.pop("error", None)
            except Exception as exc:
                status_entry["error"] = str(exc)
                logger.warning(
                    "Failed to write pre-trade snapshot for %s: %s", tid, exc
                )
            self._team_runtime_status[tid] = status_entry

        # Execute strategies for each team in parallel
        tasks: List[asyncio.Task[None]] = []
        for tid, team in self.teams.items():
            if not should_run_map.get(tid, False):
                continue
            tasks.append(
                asyncio.create_task(
                    self._execute_team_strategy(team, bars, current_prices)
                )
            )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for team, res in zip(self.teams.values(), results):
                if isinstance(res, Exception):
                    logger.error("Strategy task error for team %s: %s", team.name, res)

        # Append metrics snapshot if available (post-trade)
        for tid, team in self.teams.items():
            metrics = performance_tracker.calculate_performance_metrics(tid)
            if isinstance(metrics, dict) and "error" not in metrics:
                trade_executor.appendMetrics(tid, metrics)

        # Global (account-level) snapshot from Alpaca and metrics
        global_source = "alpaca"
        gsnap = trade_executor.fetchGlobalSnapshotFromBroker()
        if gsnap is None:
            global_source = "aggregate"
            gsnap = trade_executor.buildGlobalSnapshot(self.teams, current_prices)
        if gsnap is not None:
            gsnap.timestamp = minute_mark
            trade_executor.appendGlobalPortfolioSnapshot(gsnap)
            self._globalHistory.append(
                {"timestamp": gsnap.timestamp, "value": float(gsnap.market_value)}
            )
            gmetrics = self._computeGlobalMetrics()
            if gmetrics:
                trade_executor.appendGlobalMetrics(gmetrics)
            self._last_global_snapshot = {
                "timestamp": gsnap.timestamp.isoformat(),
                "cash": _to_float(gsnap.cash),
                "market_value": _to_float(gsnap.market_value),
                "source": global_source,
                "positions_count": len(gsnap.positions),
                "positions": [
                    {
                        "symbol": sym,
                        "quantity": _to_float(pos.quantity),
                        "side": pos.side,
                        "value": _to_float(pos.value),
                    }
                    for sym, pos in gsnap.positions.items()
                ],
            }

        # At UTC day rollover, fold yesterday's JSONL into Parquet and delete JSONL
        today = datetime.now(timezone.utc).date()
        if self._lastPortfolioFoldDay is None or self._lastPortfolioFoldDay != today:
            prev = today - timedelta(days=1)
            for team_id in list(self.teams.keys()):
                try:
                    trade_executor.foldDailyPortfolio(team_id, prev)
                except Exception as e:
                    logger.warning(
                        "Failed to fold portfolio for %s on %s: %s",
                        team_id,
                        prev,
                        e,
                    )
            try:
                trade_executor.foldDailyGlobalPortfolio(prev)
            except Exception as e:
                logger.warning("Failed to fold global portfolio on %s: %s", prev, e)
            self._lastPortfolioFoldDay = today

        symbols_for_status = (
            sorted(bars_by_symbol.keys())
            if bars_by_symbol
            else sorted(current_prices.keys())
        )
        self._write_runtime_status(minute_mark, symbols_for_status, bar_count)

    def _write_runtime_status(
        self, minute_mark: datetime, symbols: List[str], bar_count: int
    ) -> None:
        payload: Dict[str, Any] = {
            "timestamp": minute_mark.isoformat(),
            "symbols": symbols,
            "bar_count": bar_count,
            "running": self.running,
            "teams": list(self._team_runtime_status.values()),
        }
        if self._last_global_snapshot:
            payload["global"] = self._last_global_snapshot
        try:
            self._status_path.write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:
            logger.debug("Failed to persist runtime status: %s", exc)

    def _computeGlobalMetrics(self) -> Optional[Dict[str, Any]]:
        """Compute simple metrics from global history for this session."""
        hist = self._globalHistory
        if len(hist) < 2:
            return None
        import math

        values = [h["value"] for h in hist]
        start, end = values[0], values[-1]
        total_return = (end - start) / start if start > 0 else 0.0
        rets = []
        for i in range(1, len(values)):
            prev = values[i - 1]
            if prev > 0:
                rets.append((values[i] - prev) / prev)
        if not rets:
            return {
                "returns": {
                    "start_value": start,
                    "end_value": end,
                    "total_return": total_return,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                }
            }
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        std = math.sqrt(var)
        minutes_per_year = 390 * 252
        sharpe = (
            (mean * minutes_per_year - 0.05) / (std * (minutes_per_year**0.5))
            if std > 0
            else 0.0
        )
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return {
            "returns": {
                "start_value": start,
                "end_value": end,
                "total_return": total_return,
                "sharpe_ratio": sharpe,
                "max_drawdown": max_dd,
            }
        }

    async def _execute_team_strategy(
        self, team: Team, bars: List[MinuteBar], current_prices: Dict[str, Decimal]
    ) -> None:
        """Execute strategy for a specific team"""
        # Load on first use and cache per team
        team_key = team.name
        strat = self._loaded_strategies.get(team_key)
        if strat is None:
            if not team.strategy.repoPath or not team.strategy.entryPoint:
                logger.warning(f"No strategy configured for team {team.name}")
                return
            try:
                strat = load_strategy_from_folder(
                    team.strategy.repoPath, team.strategy.entryPoint
                )
                self._loaded_strategies[team_key] = strat
            except Exception as e:
                error_handler_instance.handle_strategy_error(
                    strategy_name=str(team.strategy.entryPoint),
                    error=e,
                    team_id=team_key,
                )
                return

        # Prepare IO payloads expected by user strategies
        team_io: Dict[str, Any] = {
            "id": team.name,
            "name": team.name,
            "cash": float(team.portfolio.freeCash),
            "positions": {
                symbol: {
                    "quantity": float(pos.quantity),
                    "side": pos.side,
                    "avg_cost": float(pos.avgCost),
                }
                for symbol, pos in team.portfolio.positions.items()
            },
            "params": team.strategy.params,
            "api": self._data_api,
        }
        bars_io: Dict[str, Any] = {}
        for b in bars:
            d = bars_io.setdefault(
                b.ticker,
                {
                    "timestamp": [],
                    "open": [],
                    "high": [],
                    "low": [],
                    "close": [],
                    "volume": [],
                },
            )
            d["timestamp"].append(b.timestamp.isoformat())
            d["open"].append(float(b.open))
            d["high"].append(float(b.high))
            d["low"].append(float(b.low))
            d["close"].append(float(b.close))
            d["volume"].append(int(b.volume) if b.volume is not None else 0)
        prices_io: Dict[str, float] = {k: float(v) for k, v in current_prices.items()}

        # Generate trading signal with robust isolation (thread + timeout)
        loop = asyncio.get_running_loop()
        timeout_sec = 5
        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(
                    None, strat.generate_signal, team_io, bars_io, prices_io
                ),
                timeout=timeout_sec,
            )
        except Exception as e:
            # Log to global error handler
            error_handler_instance.handle_strategy_error(
                strategy_name=strat.__class__.__name__, error=e, team_id=team_key
            )

            # Log to team-specific error file
            error_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_type": e.__class__.__name__,
                "message": str(e),
                "strategy": strat.__class__.__name__,
                "timeout": isinstance(e, asyncio.TimeoutError),
                "phase": "signal_generation",
            }
            trade_executor.appendStrategyError(team_key, error_info)
            return
        if not raw:
            return
        try:
            signal = StrategySignal.model_validate(raw)
        except Exception as e:
            # Log to global error handler
            error_handler_instance.handle_strategy_error(
                strategy_name=strat.__class__.__name__, error=e, team_id=team_key
            )

            # Log to team-specific error file
            error_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_type": e.__class__.__name__,
                "message": str(e),
                "strategy": strat.__class__.__name__,
                "timeout": False,
                "phase": "signal_validation",
                "signal_data": str(raw)[:200],  # First 200 chars of invalid signal
            }
            trade_executor.appendStrategyError(team_key, error_info)
            return

        # Execute trade
        req = TradeRequest(
            team_id=team.name,
            symbol=signal.symbol,
            side=signal.action,
            quantity=signal.quantity,
            price=signal.price,
            order_type=signal.order_type,
            time_in_force=signal.time_in_force,
        )
        success, message = trade_executor.execute(team, req, current_prices)

        if success:
            logger.info(f"Trade executed for team {team.name}: {message}")
        else:
            logger.warning(f"Trade failed for team {team.name}: {message}")

    async def run(self) -> None:
        """Run the main trading loop"""
        logger.info("Starting QTC Alpha trading system...")
        self.running = True
        # Teams should be created via CLI (run.py) or API prior to run

        try:
            # Load pending orders from disk
            from app.services.order_tracker import order_tracker

            order_tracker.load_pending_orders()

            # Schedule daily registry sync at 01:00 UTC if a registry path is known
            if self._registry_path:
                self._daily_sync_task = asyncio.create_task(self._daily_registry_sync())

            # Start background order reconciliation (every 30 seconds)
            self._order_reconciliation_task = asyncio.create_task(
                self._reconcile_orders_loop()
            )

            # Start data repair service (15min market hours, 60min off-hours)
            await self.data_repair_service.start()

            # Start the minute service
            await self.minute_service.run()
        except Exception as e:
            logger.error(f"Error in main trading loop: {str(e)}")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown the system"""
        logger.info("Shutting down QTC Alpha trading system...")

        # Stop the minute service
        await self.minute_service.stop()

        # Stop data repair service
        await self.data_repair_service.stop()

        # Save performance data per team
        for team_id in self.teams.keys():
            performance_tracker.save_performance_data(team_id)

        # Clear cache
        cache_manager.clear_expired()

        logger.info("Shutdown complete")

    async def _reconcile_orders_loop(self) -> None:
        """
        Background job to reconcile pending orders with Alpaca.
        Runs every 30 seconds to update execution prices and order statuses.
        """
        from app.services.order_tracker import order_tracker

        logger.info("Starting background order reconciliation loop (30s interval)...")

        while self.running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                # Reconcile with broker if available
                if trade_executor._broker:
                    await order_tracker.reconcile_with_broker(trade_executor._broker)

                # Cleanup old orders once per hour (when minute == 0)
                now = datetime.now(timezone.utc)
                if now.minute == 0:
                    order_tracker.cleanup_old_orders(max_age_days=7)

            except Exception as e:
                logger.error(f"Error in order reconciliation loop: {e}")
                await asyncio.sleep(30)  # Continue despite errors

    async def _daily_registry_sync(self) -> None:
        """Sync strategy repos from the registry daily at 01:00 UTC.

        Clears the loaded strategy cache so new code is picked up lazily.
        """
        while self.running:
            now = datetime.now(timezone.utc)
            next_1am = now.replace(hour=1, minute=0, second=0, microsecond=0)
            if next_1am <= now:
                next_1am += timedelta(days=1)
            await asyncio.sleep((next_1am - now).total_seconds())
            if not self._registry_path:
                continue
            try:
                logger.info("Starting daily strategy registry sync...")
                _ = sync_all_from_registry(self._registry_path)
                # force reload on next minute for all teams
                self._loaded_strategies.clear()
                logger.info(
                    "Registry sync complete; strategies will reload on next tick"
                )
            except Exception as e:
                logger.warning(f"Daily registry sync failed: {e}")

    def get_team_performance(self, team_id: str) -> Dict[str, Any]:
        """Get performance metrics for a specific team"""
        if team_id not in self.teams:
            return {"error": "Team not found"}

        team = self.teams[team_id]
        return {
            "team_name": team.name,
            "strategy": team.strategy.name,
            "cash": float(team.portfolio.freeCash),
            "positions": {
                symbol: {
                    "quantity": float(pos.quantity),
                    "avg_cost": float(pos.avgCost),
                    "side": pos.side,
                }
                for symbol, pos in team.portfolio.positions.items()
            },
            "trade_history": trade_executor.get_trade_history(team_id),
        }

    def get_all_teams_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get performance metrics for all teams"""
        return {
            team_id: self.get_team_performance(team_id) for team_id in self.teams.keys()
        }

    def get_team_metrics(self, team_id: str) -> Dict[str, Any]:
        """High-level portfolio metrics for a team (name, cash, market value, PnL, drawdown, sharpe, trades)."""
        perf = self.get_team_performance(team_id)
        if "error" in perf:
            return perf
        # Use performance tracker metrics if available
        metrics = performance_tracker.calculate_performance_metrics(team_id)
        out = {
            "team_name": perf["team_name"],
            "strategy": perf["strategy"],
            "cash": perf["cash"],
            "positions": perf["positions"],
            "trades_made": len(perf["trade_history"]),
        }
        if "error" not in metrics:
            returns = metrics.get("returns", {})
            out.update(
                {
                    "market_value": returns.get("end_value"),
                    "pnl": returns.get("total_return"),
                    "sharpe_ratio": returns.get("sharpe_ratio"),
                    "max_drawdown": returns.get("max_drawdown"),
                }
            )
        return out

    def get_all_teams_metrics(self) -> Dict[str, Dict[str, Any]]:
        return {tid: self.get_team_metrics(tid) for tid in self.teams.keys()}


class PerformanceTracker:
    """Tracks and reports performance metrics"""

    def __init__(self) -> None:
        self.performance_history: List[Dict[str, Any]] = []
        self.start_time = datetime.now(timezone.utc)

    def update_performance(
        self, teams: Dict[str, Team], current_prices: Dict[str, Decimal]
    ) -> None:
        """Update performance metrics for all teams"""
        timestamp = datetime.now(timezone.utc)

        for team_id, team in teams.items():
            portfolio_value = team.portfolio.marketValue(current_prices)

            performance_record = {
                "timestamp": timestamp,
                "team_id": team_id,
                "team_name": team.name,
                "portfolio_value": float(portfolio_value),
                "cash": float(team.portfolio.freeCash),
                "positions": {
                    symbol: {
                        "quantity": float(pos.quantity),
                        "value": float(
                            pos.quantity * current_prices.get(symbol, Decimal("0"))
                        ),
                        "side": pos.side,
                    }
                    for symbol, pos in team.portfolio.positions.items()
                    if symbol in current_prices
                },
            }

            self.performance_history.append(performance_record)

    def save_final_report(self) -> None:
        """Save final performance report"""
        if not self.performance_history:
            return

        # Calculate summary statistics
        end_time = datetime.now(timezone.utc)
        duration = end_time - self.start_time

        # Group by team
        teams_summary = {}
        for record in self.performance_history:
            team_id = record["team_id"]
            if team_id not in teams_summary:
                teams_summary[team_id] = {
                    "team_name": record["team_name"],
                    "initial_value": record["portfolio_value"],
                    "final_value": record["portfolio_value"],
                    "max_value": record["portfolio_value"],
                    "min_value": record["portfolio_value"],
                    "records": [],
                }

            teams_summary[team_id]["records"].append(record)
            teams_summary[team_id]["final_value"] = record["portfolio_value"]
            teams_summary[team_id]["max_value"] = max(
                teams_summary[team_id]["max_value"], record["portfolio_value"]
            )
            teams_summary[team_id]["min_value"] = min(
                teams_summary[team_id]["min_value"], record["portfolio_value"]
            )

        # Calculate returns and drawdowns
        for team_id, summary in teams_summary.items():
            initial = summary["initial_value"]
            final = summary["final_value"]
            max_val = summary["max_value"]
            min_val = summary["min_value"]

            summary["total_return"] = (final - initial) / initial if initial > 0 else 0
            summary["max_drawdown"] = (
                (max_val - min_val) / max_val if max_val > 0 else 0
            )
            summary["duration_hours"] = duration.total_seconds() / 3600

        # Save to file
        report = {
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_hours": duration.total_seconds() / 3600,
            "teams_summary": teams_summary,
        }

        cache_manager.save_to_disk(report, "final_performance_report")
        logger.info("Final performance report saved")


# ----- CLI helpers (merged from run.py) -----


def setup_environment(env: str) -> None:
    os.environ["QTC_ENV"] = env
    config = EnvironmentConfig(env)
    print(f"Environment: {env}")
    print(f"Log level: {config.get('log_level')}")
    print(f"Max position size: {config.get('max_position_size')}")
    print(f"Max daily trades: {config.get('max_daily_trades')}")


REPO_ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = REPO_ROOT / "external_strategies"


def _prepare_strategy_workspace(team_id: str, source: Path) -> Path:
    STRATEGY_ROOT.mkdir(parents=True, exist_ok=True)
    dest = STRATEGY_ROOT / team_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    source = source.resolve()
    if source.is_file():
        candidate = source if source.name == "strategy.py" else None
    else:
        candidate = source / "strategy.py"
        if not candidate.exists():
            matches = list(source.rglob("strategy.py"))
            candidate = matches[0] if matches else None

    if candidate is None:
        raise FileNotFoundError(f"strategy.py not found in {source}")

    shutil.copy2(candidate, dest / "strategy.py")
    return dest


def _load_teams_from_registry(
    registry_path: str, do_sync: bool
) -> List[Dict[str, Any]]:
    reg = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
    teams: List[Dict[str, Any]] = reg.get("teams", []) or []
    out: List[Dict[str, Any]] = []

    # BEFORE:
    # results: Dict[str, Dict[str, Any]] = {}
    # if do_sync and any("git_url" in t for t in teams):
    #     results = sync_all_from_registry(registry_path)

    for item in teams:
        raw_name = item.get("team_id") or item.get("name") or "team"
        name = slugify(raw_name)
        entry_point = item.get("entry_point", "strategy:Strategy")
        cash = Decimal(str(item.get("initial_cash", "10000")))
        run_24_7 = bool(item.get("run_24_7", False))
        params = item.get("params", {}) or {}

        repo_dir: Optional[Path] = None

        if do_sync and item.get("git_url"):
            # Use the SAME logic as CLI: call pullstrat(name) which:
            # - resolves ref -> sha
            # - clones into cache
            # - copies strategy.py to external_strategies/<team_id>
            # - updates team_registry.yaml repo_dir
            tm_pullstrat(name)
            # re-read registry to pick up repo_dir set by pullstrat
            fresh = _load_registry()
            for t in fresh.get("teams", []):
                if (t.get("team_id") or t.get("name")) == name and t.get("repo_dir"):
                    repo_dir = Path(t["repo_dir"])
                    break
            if not repo_dir:
                print(f"Skipping team {name}: pullstrat didn't set repo_dir")
                continue
        else:
            repo_val = item.get("repo_dir")
            if repo_val:
                repo_dir = Path(repo_val)
            else:
                print(
                    f"Skipping team {name}: no repo_dir; run 'team_manage pullstrat {name}'"
                )
                continue

        try:
            # If repo_dir already points to external_strategies/<team_id>, do not
            # re-prepare (which would delete the folder we just synced). Just use it.
            use_repo = repo_dir
            try:
                strat_root = STRATEGY_ROOT.resolve()
                if use_repo.resolve().is_dir() and (
                    use_repo.resolve() == (strat_root / name).resolve()
                ):
                    if not (use_repo / "strategy.py").exists():
                        raise FileNotFoundError(f"strategy.py not found in {use_repo}")
                    stable = use_repo
                else:
                    stable = _prepare_strategy_workspace(name, use_repo)
            except Exception:
                # Fallback to prepare workspace if any path resolution check fails
                stable = _prepare_strategy_workspace(name, use_repo)
        except Exception as exc:
            print(f"Skipping team {name}: could not prepare strategy ({exc})")
            continue

        combined_params = dict(params)
        combined_params.setdefault("run_24_7", run_24_7)

        out.append(
            {
                "team_id": name,
                "repo_dir": str(stable),
                "entry_point": entry_point,
                "initial_cash": cash,
                "params": combined_params,
                "run_24_7": run_24_7,
            }
        )

    return out


async def run_trading_system(
    teams_config: List[Dict[str, Any]],
    duration_minutes: Optional[int] = None,
) -> None:
    orchestrator = QTCAlphaOrchestrator()
    for cfg in teams_config:
        name = cfg["team_id"]
        repo_path = cfg["repo_dir"]
        entry_point = cfg["entry_point"]
        initial_cash = cfg["initial_cash"]
        params = dict(cfg.get("params", {}))
        params.setdefault("run_24_7", cfg.get("run_24_7", False))

        orchestrator.create_team(
            name, repo_path, entry_point, initial_cash, params=params
        )
        # Ensure API key exists for the team slug (not random UUID)
        try:
            from app.services.auth import auth_manager as _am

            _am.generateKey(name)
        except Exception:
            pass
        print(
            f"Created team: {name} with strategy {entry_point} at {repo_path} and ${initial_cash} initial capital"
        )

        orchestrator._reconcile_teams_with_registry()
    print("Press Ctrl+C to stop gracefully")
    try:
        if duration_minutes:
            await asyncio.wait_for(orchestrator.run(), timeout=duration_minutes * 60)
        else:
            await orchestrator.run()
    except asyncio.TimeoutError:
        print(f"\nTrading system stopped after {duration_minutes} minutes")
    except KeyboardInterrupt:
        print("\nTrading system stopped by user")
    finally:
        await orchestrator.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="QTC Alpha Trading System")
    parser.add_argument(
        "--env", choices=["development", "production", "testing"], default="development"
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run duration in minutes (default: run indefinitely)",
    )
    # Orchestrator always loads teams from team_registry.yaml in repo root.
    parser.add_argument(
        "--test", action="store_true", help="Run in test mode with limited universe"
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("QTC_LOG_LEVEL", "INFO"),
        help="Root logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=os.getenv("QTC_LOG_PATH"),
        help="Optional path for general log output",
    )
    parser.add_argument(
        "--error-log-file",
        default=os.getenv("QTC_ERROR_LOG"),
        help="Optional override for error log output",
    )
    parser.add_argument(
        "--print-team",
        type=str,
        help="Print latest portfolio and metrics for team_id then exit",
    )
    parser.add_argument(
        "--print-global",
        action="store_true",
        help="Print latest global portfolio and metrics then exit",
    )

    args = parser.parse_args()

    log_level = args.log_level or "INFO"
    log_file = args.log_file or None
    try:
        configure_logging(log_level, log_file)
    except ValueError as exc:
        print(f"Invalid log level '{log_level}': {exc}")
        sys.exit(2)

    error_log_file = args.error_log_file or None
    if error_log_file:
        error_handler_instance.configure(error_log_file)

    if args.test:
        args.env = "testing"
    setup_environment(args.env)

    # On-demand status printing
    if args.print_team:
        _print_team_status(args.print_team)
        sys.exit(0)
    if args.print_global:
        _print_global_status()
        sys.exit(0)

    # Always load from repository-root team_registry.yaml and sync repos
    default_registry = Path(__file__).parents[1] / "team_registry.yaml"
    if not default_registry.exists():
        print("team_registry.yaml not found in repository root. Please add your teams.")
        sys.exit(1)
    print(f"Loading teams from {default_registry} and syncing repos...")
    teams_config: List[Dict[str, Any]] = _load_teams_from_registry(
        str(default_registry), do_sync=True
    )
    if not teams_config:
        print("No valid teams found in team_registry.yaml.")
        sys.exit(1)

    asyncio.run(run_trading_system(teams_config, args.duration))

    # Print error summary
    error_summary = error_handler_instance.get_error_summary()
    if error_summary["total_errors"] > 0:
        print("\nError Summary:")
        print(f"Total errors: {error_summary['total_errors']}")
        for error_type, count in error_summary["error_counts"].items():
            print(f"  {error_type}: {count}")
    else:
        print("\nNo errors encountered during execution.")


def _tail_jsonl(path: Path) -> Optional[Dict[str, Any]]:
    if not path or not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read = min(16384, size)
            f.seek(size - read)
            chunk = f.read().decode("utf-8", errors="ignore")
            lines = [ln for ln in chunk.splitlines() if ln.strip()]
            import json

            for ln in reversed(lines):
                try:
                    return json.loads(ln)
                except Exception:
                    continue
    except Exception:
        return None
    return None


def _print_team_status(team_id: str) -> None:
    cfg = EnvironmentConfig(os.getenv("QTC_ENV", "development"))
    root = cfg.get_data_path(f"team/{team_id}")
    port_dir = root / "portfolio"
    latest_json = None
    if port_dir.exists():
        files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
        if files:
            latest_json = files[-1]
    snap = _tail_jsonl(latest_json) if latest_json is not None else None
    metrics = _tail_jsonl(root / "metrics.jsonl")
    print(f"Team {team_id} status:")
    if snap:
        print("Portfolio Snapshot:")
        print(snap)
    else:
        print("No portfolio snapshot found.")
    if metrics and isinstance(metrics, dict):
        print("Metrics:")
        print(metrics)
    else:
        print("No metrics found.")


def _print_global_status() -> None:
    cfg = EnvironmentConfig(os.getenv("QTC_ENV", "development"))
    root = cfg.get_data_path("qtc-alpha")
    port_dir = cfg.get_data_path("qtc-alpha/portfolio")
    latest_json = None
    if port_dir.exists():
        files = sorted([p for p in port_dir.glob("*.jsonl") if p.is_file()])
        if files:
            latest_json = files[-1]
    snap = _tail_jsonl(latest_json) if latest_json is not None else None
    metrics = _tail_jsonl(root / "metrics.jsonl")
    print("Global account status:")
    if snap:
        print("Portfolio Snapshot:")
        print(snap)
    else:
        print("No portfolio snapshot found.")
    if metrics and isinstance(metrics, dict):
        print("Metrics:")
        print(metrics)
    else:
        print("No metrics found.")


if __name__ == "__main__":
    main()
