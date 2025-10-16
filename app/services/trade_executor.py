from decimal import Decimal
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Tuple
from app.models.teams import Team, Position, Side, OrderType
from app.adapters.alpaca_broker import load_broker_from_env
from app.services.caching import cache_manager
from app.services.market_hours import is_symbol_trading
from app.models.trading import (
    TradeRequest,
    TradeRecord,
    PortfolioSnapshot,
    PositionView,
    PendingOrder,
)
from app.telemetry import record_activity
from app.config.environments import config
import logging

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Handles trade execution, position management, and basic limits."""

    def __init__(
        self,
        slippage_rate: Decimal = Decimal("0"),
    ):
        self.daily_trade_count: Dict[str, int] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self._broker = load_broker_from_env()

    def execute(
        self,
        team: Team,
        req: TradeRequest,
        current_prices: Optional[Dict[str, Decimal]] = None,
    ) -> Tuple[bool, str]:
        """Execute a trade using minimal risk checks and best-effort broker routing."""
        try:
            symbol = req.symbol
            side = req.side
            quantity = req.quantity
            price = req.price
            order_type = req.order_type
            now = datetime.now(timezone.utc)
            if not is_symbol_trading(symbol, now):
                return False, f"Market closed for {symbol} at {now.isoformat()}"

            if not self._validate_trade(team, symbol, side, quantity, price):
                return False, "Trade validation failed"

            execution_price = self._calculate_execution_price(price, side)

            broker_order_id: Optional[str] = None
            broker_error: Optional[str] = None
            should_update_portfolio = True  # Track if we should update portfolio
            
            if self._broker is not None and order_type in ("market", "limit"):
                try:
                    client_id = f"{req.team_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
                    
                    # Place order based on type
                    if order_type == "market":
                        order_id = self._broker.placeMarketOrder(
                            symbol, side, quantity, clientOrderId=client_id
                        )
                    elif order_type == "limit":
                        order_id = self._broker.placeLimitOrder(
                            symbol, side, quantity, limit_price=price,
                            time_in_force=req.time_in_force, clientOrderId=client_id
                        )
                    
                    broker_order_id = order_id
                    logger.info(
                        "Alpaca %s order submitted: %s for %s %s %s @ %s",
                        order_type,
                        order_id,
                        symbol,
                        side,
                        quantity,
                        price,
                    )
                    
                    # Handle order type-specific logic
                    if order_type == "market":
                        # Get actual execution price from Alpaca for market orders
                        try:
                            import time
                            time.sleep(0.5)  # Brief delay to allow order to fill
                            order_details = self._broker.getOrderById(order_id)
                            filled_price = order_details.get("filled_avg_price")
                            if filled_price is not None:
                                execution_price = Decimal(str(filled_price))
                                logger.info(
                                    "Alpaca execution price: %s (requested: %s)",
                                    execution_price,
                                    price,
                                )
                        except Exception as ep:  # noqa: BLE001
                            logger.warning(
                                "Could not retrieve execution price for order %s: %s",
                                order_id,
                                ep,
                            )
                            # Fall back to requested price
                        # Market orders update portfolio immediately
                        should_update_portfolio = True
                        
                    elif order_type == "limit":
                        # Store as pending order - will be reconciled later
                        from app.services.order_tracker import order_tracker
                        
                        pending_order = PendingOrder(
                            order_id=order_id,
                            team_id=req.team_id,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            order_type=order_type,
                            limit_price=price,
                            status="new",
                            filled_qty=Decimal("0"),
                            filled_avg_price=None,
                            time_in_force=req.time_in_force,
                            created_at=datetime.now(timezone.utc),
                            broker_order_id=order_id,
                            requested_price=price,
                        )
                        order_tracker.store_pending_order(pending_order)
                        logger.info(
                            f"Stored pending limit order {order_id} for {symbol} - "
                            f"will reconcile in background"
                        )
                        # Don't update portfolio yet - wait for fill
                        should_update_portfolio = False
                        return True, f"Limit order placed: {order_id}"
                    
                except Exception as be:  # noqa: BLE001
                    broker_error = str(be)
                    logger.error("Alpaca order submission failed: %s", be)

            # For market orders or local-only: update portfolio immediately
            if should_update_portfolio:
                success = self._update_portfolio(
                    team, symbol, side, quantity, execution_price
                )
            else:
                # Limit order stored as pending, don't update portfolio yet
                success = True

            if success:
                tr = TradeRecord(
                    team_id=team.name,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    requested_price=price,
                    execution_price=execution_price,
                    order_type=order_type,
                    broker_order_id=broker_order_id,
                )
                self.trade_history.append(tr.model_dump())

                team_key = team.name
                self.daily_trade_count[team_key] = (
                    self.daily_trade_count.get(team_key, 0) + 1
                )

                cache_manager.cache_strategy_result(
                    team_key,
                    {
                        "portfolio": team.portfolio.model_dump(),
                        "last_trade": tr.model_dump(),
                    },
                )

                self.appendTradeRecord(tr)
                snap = self.buildSnapshot(
                    team,
                    current_prices,
                    touchedSymbol=symbol,
                    touchedPrice=execution_price,
                )
                self.appendPortfolioSnapshot(snap)

                activity = f"{team.name} {side} {quantity} {symbol} @ {float(execution_price):.4f}"
                if broker_error:
                    activity += f" (broker error: {broker_error})"
                record_activity(activity)
                if broker_error:
                    return True, f"Trade executed locally; broker error: {broker_error}"
                return True, "Trade executed successfully"

            return False, "Portfolio update failed"

        except Exception as e:  # noqa: BLE001
            logger.error("Trade execution failed for team %s: %s", team.name, e)
            return False, f"Trade execution error: {str(e)}"

    def execute_trade(
        self,
        team: Team,
        symbol: str,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        order_type: OrderType = "market",
    ) -> Tuple[bool, str]:
        """Execute a trade for a team (legacy helper)."""
        try:
            if not self._validate_trade(team, symbol, side, quantity, price):
                return False, "Trade validation failed"

            execution_price = self._calculate_execution_price(price, side)

            broker_error: Optional[str] = None
            broker_order_id: Optional[str] = None
            if self._broker is not None and order_type in ("market", "limit"):
                try:
                    client_id = f"{team.name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
                    
                    # Place order based on type
                    if order_type == "market":
                        order_id = self._broker.placeMarketOrder(
                            symbol, side, quantity, clientOrderId=client_id
                        )
                    elif order_type == "limit":
                        order_id = self._broker.placeLimitOrder(
                            symbol, side, quantity, limit_price=price,
                            clientOrderId=client_id
                        )
                    
                    broker_order_id = order_id
                    logger.info(
                        "Alpaca %s order submitted: %s for %s %s %s @ %s",
                        order_type,
                        order_id,
                        symbol,
                        side,
                        quantity,
                        price,
                    )
                    
                    # Get actual execution price for market orders
                    if order_type == "market":
                        try:
                            import time
                            time.sleep(0.5)
                            order_details = self._broker.getOrderById(order_id)
                            filled_price = order_details.get("filled_avg_price")
                            if filled_price is not None:
                                execution_price = Decimal(str(filled_price))
                        except Exception as ep:  # noqa: BLE001
                            logger.warning(
                                "Could not retrieve execution price for order %s: %s",
                                order_id,
                                ep,
                            )
                    elif order_type == "limit":
                        # Store as pending order for background reconciliation
                        from app.services.order_tracker import order_tracker
                        
                        pending_order = PendingOrder(
                            order_id=broker_order_id,
                            team_id=team.name,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            order_type=order_type,
                            limit_price=price,
                            status="new",
                            filled_qty=Decimal("0"),
                            filled_avg_price=None,
                            time_in_force="day",
                            created_at=datetime.now(timezone.utc),
                            broker_order_id=broker_order_id,
                            requested_price=price,
                        )
                        order_tracker.store_pending_order(pending_order)
                        return True, f"Limit order placed: {broker_order_id}"
                    
                except Exception as be:  # noqa: BLE001
                    broker_error = str(be)
                    logger.error("Alpaca order submission failed: %s", be)

            success = self._update_portfolio(
                team, symbol, side, quantity, execution_price
            )

            if success:
                trade_record = {
                    "team_id": team.name,
                    "symbol": symbol,
                    "side": side,
                    "quantity": float(quantity),
                    "price": float(execution_price),
                    "timestamp": datetime.now(timezone.utc),
                    "order_type": order_type,
                }
                self.trade_history.append(trade_record)

                team_key = team.name
                self.daily_trade_count[team_key] = (
                    self.daily_trade_count.get(team_key, 0) + 1
                )

                cache_manager.cache_strategy_result(
                    team_key,
                    {
                        "portfolio": team.portfolio.model_dump(),
                        "last_trade": trade_record,
                    },
                )

                activity = f"{team.name} {side} {quantity} {symbol} @ {float(execution_price):.4f}"
                if broker_error:
                    activity += f" (broker error: {broker_error})"
                record_activity(activity)
                if broker_error:
                    return True, f"Trade executed locally; broker error: {broker_error}"
                return True, "Trade executed successfully"

            return False, "Portfolio update failed"

        except Exception as e:  # noqa: BLE001
            logger.error("Trade execution failed for team %s: %s", team.name, e)
            return False, f"Trade execution error: {str(e)}"

    def _validate_trade(
        self, team: Team, symbol: str, side: Side, quantity: Decimal, price: Decimal
    ) -> bool:
        """Validate strictly by cash (buys) or available position (sells)."""
        if side == "buy":
            trade_value = quantity * price
            if team.portfolio.freeCash < trade_value:
                logger.warning(f"Insufficient funds for team {team.name}")
                return False
        else:
            current_position = team.portfolio.positions.get(symbol)
            if not current_position or current_position.quantity < quantity:
                logger.warning(
                    f"Insufficient position for sell order for team {team.name}"
                )
                return False
        return True

    def _calculate_execution_price(
        self, requested_price: Decimal, side: Side
    ) -> Decimal:
        """Return requested price unchanged (no simulated slippage)."""
        return requested_price

    def _update_portfolio(
        self, team: Team, symbol: str, side: Side, quantity: Decimal, price: Decimal
    ) -> bool:
        """Update team portfolio with new trade"""
        try:
            if side == "buy":
                # Add to position
                if symbol in team.portfolio.positions:
                    existing_pos = team.portfolio.positions[symbol]
                    # Calculate new average cost
                    total_cost = (existing_pos.quantity * existing_pos.avgCost) + (
                        quantity * price
                    )
                    total_quantity = existing_pos.quantity + quantity
                    new_avg_cost = total_cost / total_quantity

                    team.portfolio.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=total_quantity,
                        side="buy",
                        avgCost=new_avg_cost,
                        costBasis=total_quantity * new_avg_cost,
                        openedAt=existing_pos.openedAt,
                    )
                else:
                    team.portfolio.positions[symbol] = Position.fromTrade(
                        symbol, quantity, "buy", price
                    )

                # Deduct cash
                team.portfolio.freeCash -= quantity * price

            else:  # sell
                # Reduce position
                if symbol in team.portfolio.positions:
                    existing_pos = team.portfolio.positions[symbol]
                    new_quantity = existing_pos.quantity - quantity

                    if new_quantity <= 0:
                        # Close position entirely
                        del team.portfolio.positions[symbol]
                    else:
                        # Update position
                        team.portfolio.positions[symbol] = Position(
                            symbol=symbol,
                            quantity=new_quantity,
                            side=existing_pos.side,
                            avgCost=existing_pos.avgCost,
                            costBasis=new_quantity * existing_pos.avgCost,
                            openedAt=existing_pos.openedAt,
                        )

                # Add cash
                team.portfolio.freeCash += quantity * price

            # Update team timestamp
            team.updatedAt = datetime.now(timezone.utc)
            return True

        except Exception as e:
            logger.error(f"Portfolio update failed: {str(e)}")
            return False

    def get_portfolio_value(
        self, team: Team, current_prices: Dict[str, Decimal]
    ) -> Decimal:
        """Calculate current portfolio value"""
        return team.portfolio.marketValue(current_prices)

    def get_position_pnl(
        self, team: Team, symbol: str, current_price: Decimal
    ) -> Decimal:
        """Calculate P&L for a specific position"""
        if symbol not in team.portfolio.positions:
            return Decimal("0")

        position = team.portfolio.positions[symbol]
        current_value = position.quantity * current_price
        cost_basis = position.costBasis

        if position.side == "buy":
            return current_value - cost_basis
        else:  # short position
            return cost_basis - current_value

    def reset_daily_counts(self) -> None:
        """Reset daily trade counts (call at start of each day)"""
        self.daily_trade_count.clear()
        logger.info("Daily trade counts reset")

    def get_trade_history(self, team_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get trade history, optionally filtered by team"""
        if team_id:
            return [
                trade for trade in self.trade_history if trade["team_id"] == team_id
            ]
        return self.trade_history.copy()

    # ----- persistence helpers -----
    def appendTradeRecord(self, tr: TradeRecord) -> None:
        team_dir = config.get_data_path(f"team/{tr.team_id}")
        team_dir.mkdir(parents=True, exist_ok=True)
        path = team_dir / "trades.jsonl"
        import json

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(tr.model_dump(), default=str) + "\n")

    def appendPortfolioSnapshot(self, snap: PortfolioSnapshot) -> None:
        team_dir = config.get_data_path(f"team/{snap.team_id}/portfolio")
        team_dir.mkdir(parents=True, exist_ok=True)
        # Write to daily JSONL file per team in team directory
        day = snap.timestamp.date()
        path = team_dir / f"{day.isoformat()}.jsonl"
        import json

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap.model_dump(), default=str) + "\n")
        logger.debug("Portfolio snapshot written for team %s at %s", snap.team_id, path)

    def buildSnapshot(
        self,
        team: Team,
        current_prices: Optional[Dict[str, Decimal]],
        *,
        touchedSymbol: Optional[str] = None,
        touchedPrice: Optional[Decimal] = None,
    ) -> PortfolioSnapshot:
        prices: Dict[str, Decimal] = {}
        if current_prices:
            prices.update(current_prices)
        if touchedSymbol is not None and touchedPrice is not None:
            prices[touchedSymbol] = touchedPrice

        # Build position views
        pos_views: Dict[str, PositionView] = {}
        for sym, pos in team.portfolio.positions.items():
            price = prices.get(sym, pos.avgCost)
            value = pos.quantity * price
            if pos.side == "buy":
                pnl_unrealized = value - pos.quantity * pos.avgCost
            else:
                pnl_unrealized = pos.quantity * pos.avgCost - value
            pos_views[sym] = PositionView(
                symbol=sym,
                quantity=pos.quantity,
                side=pos.side,
                avg_cost=pos.avgCost,
                value=value,
                pnl_unrealized=pnl_unrealized,
            )

        market_value = team.portfolio.freeCash + sum(
            v.value for v in pos_views.values()
        )

        return PortfolioSnapshot(
            team_id=team.name,
            cash=team.portfolio.freeCash,
            positions=pos_views,
            market_value=market_value,
        )

    # ----- global (account-level) helpers -----
    def buildGlobalSnapshot(
        self, teams: Dict[str, Team], current_prices: Optional[Dict[str, Decimal]]
    ) -> PortfolioSnapshot:
        prices: Dict[str, Decimal] = current_prices.copy() if current_prices else {}
        total_cash = Decimal("0")
        agg_positions: Dict[str, Dict[str, Decimal]] = {}

        for team in teams.values():
            total_cash += team.portfolio.freeCash
            for sym, pos in team.portfolio.positions.items():
                price = prices.get(sym, pos.avgCost)
                entry = agg_positions.setdefault(
                    sym,
                    {"qty": Decimal("0"), "value": Decimal("0"), "cost": Decimal("0")},
                )
                entry["qty"] += pos.quantity
                entry["value"] += pos.quantity * price
                entry["cost"] += pos.quantity * pos.avgCost

        pos_views: Dict[str, PositionView] = {}
        for sym, vals in agg_positions.items():
            qty = vals["qty"]
            if qty == 0:
                continue
            value = vals["value"]
            cost_basis = vals["cost"]
            side: Side = "buy" if qty >= 0 else "sell"
            avg_cost = (cost_basis / qty) if qty != 0 else Decimal("0")
            pnl_unreal = value - cost_basis if side == "buy" else cost_basis - value
            pos_views[sym] = PositionView(
                symbol=sym,
                quantity=qty,
                side=side,
                avg_cost=avg_cost,
                value=value,
                pnl_unrealized=pnl_unreal,
            )

        market_value = total_cash + sum(v.value for v in pos_views.values())
        return PortfolioSnapshot(
            team_id="qtc-alpha",
            cash=total_cash,
            positions=pos_views,
            market_value=market_value,
        )

    def appendGlobalPortfolioSnapshot(self, snap: PortfolioSnapshot) -> None:
        root = config.get_data_path("qtc-alpha/portfolio")
        root.mkdir(parents=True, exist_ok=True)
        day = snap.timestamp.date()
        path = root / f"{day.isoformat()}.jsonl"
        import json

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap.model_dump(), default=str) + "\n")
        logger.debug("Global snapshot appended at %s", path)

    def fetchGlobalSnapshotFromBroker(self) -> Optional[PortfolioSnapshot]:
        """Build a global account snapshot directly from Alpaca account and positions."""
        if self._broker is None:
            return None
        try:
            info = self._broker.getAccountInfo()
            positions = self._broker.getPositions()
            # Convert strings to Decimals where applicable
            from decimal import Decimal as D

            cash = D(str(info.get("cash", "0")))
            pos_views: Dict[str, PositionView] = {}
            for p in positions:
                sym = p["symbol"]
                qty = D(str(p["qty"]))
                side: Side = "buy" if (str(p.get("side", "long")) == "long") else "sell"
                avg_cost = D(str(p.get("avg_entry_price", "0")))
                mval = p.get("market_value")
                if mval is not None:
                    value = D(str(mval))
                else:
                    value = qty * avg_cost
                u_pl = p.get("unrealized_pl")
                pnl = D(str(u_pl)) if u_pl is not None else None
                pos_views[sym] = PositionView(
                    symbol=sym,
                    quantity=qty,
                    side=side,
                    avg_cost=avg_cost,
                    value=value,
                    pnl_unrealized=pnl,
                )
            # Prefer account portfolio_value if present
            pv = info.get("portfolio_value")
            if pv is not None:
                market_value = D(str(pv))
            else:
                market_value = cash + sum(v.value for v in pos_views.values())
            return PortfolioSnapshot(
                team_id="qtc-alpha",
                cash=cash,
                positions=pos_views,
                market_value=market_value,
            )
        except Exception:
            return None

    def foldDailyGlobalPortfolio(self, day: date) -> None:
        import json
        import pandas as pd

        root = config.get_data_path("qtc-alpha/portfolio")
        json_path = root / f"{day.isoformat()}.jsonl"
        if not json_path.exists():
            return
        rows: List[Dict[str, Any]] = []
        with open(json_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if not rows:
            try:
                json_path.unlink()
            except Exception:
                pass
            return

        for r in rows:
            if isinstance(r.get("positions"), dict):
                try:
                    r["positionsJson"] = json.dumps(r["positions"], default=str)
                except Exception:
                    r["positionsJson"] = "{}"
            r.pop("positions", None)

        df_new = pd.DataFrame(rows)
        for col in ("cash", "market_value"):
            if col in df_new.columns:
                df_new[col] = pd.to_numeric(df_new[col], errors="coerce")
        if "timestamp" in df_new.columns:
            df_new["timestamp"] = pd.to_datetime(
                df_new["timestamp"], utc=True, errors="coerce"
            )

        pq_path = root / "portfolio.parquet"
        if pq_path.exists():
            try:
                df_old = pd.read_parquet(pq_path)
                df_all = pd.concat([df_old, df_new], ignore_index=True)
            except Exception:
                df_all = df_new
        else:
            df_all = df_new

        for col in ("cash", "market_value"):
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors="coerce")

        if "timestamp" in df_all.columns:
            df_all = df_all.sort_values("timestamp").drop_duplicates(
                subset=["timestamp"], keep="last"
            )

        df_all.to_parquet(pq_path, engine="pyarrow", index=False)
        try:
            json_path.unlink()
        except Exception:
            pass

    def appendGlobalMetrics(self, metrics: Dict[str, Any]) -> None:
        root = config.get_data_path("qtc-alpha")
        root.mkdir(parents=True, exist_ok=True)
        path = root / "metrics.jsonl"
        import json

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, default=str) + "\n")

    def foldDailyPortfolio(self, team_id: str, day: date) -> None:
        """Append the day's JSONL snapshots into a Parquet file and remove the JSONL.

        Writes/updates data/portfolio/<team_id>.parquet
        Reads and deletes data/portfolio/<team_id>-YYYY-MM-DD.jsonl
        """
        import json
        import pandas as pd

        port_dir = config.get_data_path(f"team/{team_id}/portfolio")
        json_path = port_dir / f"{day.isoformat()}.jsonl"
        if not json_path.exists():
            return
        rows: List[Dict[str, Any]] = []
        with open(json_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if not rows:
            try:
                json_path.unlink()
            except Exception:
                pass
            return

        # Normalize positions as JSON string for compactness
        for r in rows:
            if isinstance(r.get("positions"), dict):
                try:
                    r["positionsJson"] = json.dumps(r["positions"], default=str)
                except Exception:
                    r["positionsJson"] = "{}"
            r.pop("positions", None)

        df_new = pd.DataFrame(rows)
        for col in ("cash", "market_value"):
            if col in df_new.columns:
                df_new[col] = pd.to_numeric(df_new[col], errors="coerce")
        # Ensure timestamp is datetime
        if "timestamp" in df_new.columns:
            df_new["timestamp"] = pd.to_datetime(
                df_new["timestamp"], utc=True, errors="coerce"
            )

        pq_path = port_dir / "portfolio.parquet"
        if pq_path.exists():
            try:
                df_old = pd.read_parquet(pq_path)
                df_all = pd.concat([df_old, df_new], ignore_index=True)
            except Exception:
                df_all = df_new
        else:
            df_all = df_new

        for col in ("cash", "market_value"):
            if col in df_all.columns:
                df_all[col] = pd.to_numeric(df_all[col], errors="coerce")

        # Sort by timestamp and drop duplicates
        if "timestamp" in df_all.columns:
            df_all = df_all.sort_values("timestamp").drop_duplicates(
                subset=["timestamp"], keep="last"
            )

        df_all.to_parquet(pq_path, engine="pyarrow", index=False)
        try:
            json_path.unlink()
        except Exception:
            pass

    def appendMetrics(self, team_id: str, metrics: Dict[str, Any]) -> None:
        """Append a metrics snapshot as JSONL under team folder."""
        team_dir = config.get_data_path(f"team/{team_id}")
        team_dir.mkdir(parents=True, exist_ok=True)
        path = team_dir / "metrics.jsonl"
        import json

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, default=str) + "\n")

    def appendStrategyError(self, team_id: str, error_info: Dict[str, Any]) -> None:
        """Log strategy execution errors per team.
        
        Args:
            team_id: Team identifier
            error_info: Dictionary containing error details (timestamp, error_type, message, etc.)
        """
        team_dir = config.get_data_path(f"team/{team_id}")
        team_dir.mkdir(parents=True, exist_ok=True)
        error_file = team_dir / "errors.jsonl"
        import json
        
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(error_info, default=str) + "\n")
        logger.debug("Strategy error logged for team %s: %s", team_id, error_info.get("error_type"))


# Global trade executor instance
trade_executor = TradeExecutor()
