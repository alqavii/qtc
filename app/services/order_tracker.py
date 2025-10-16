"""
Order Tracker Service

Manages pending orders and reconciles with Alpaca for execution price updates.
Handles limit orders that may not fill immediately.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from decimal import Decimal

from app.models.trading import PendingOrder, TradeRecord
from app.config.environments import config

logger = logging.getLogger(__name__)


class OrderTracker:
    """
    Tracks pending orders and reconciles with broker for status updates.
    """
    
    def __init__(self):
        self.pending_orders: Dict[str, PendingOrder] = {}  # order_id -> PendingOrder
        
    def store_pending_order(self, order: PendingOrder) -> None:
        """
        Store a pending order to track.
        
        Args:
            order: PendingOrder instance
        """
        # Add to memory
        self.pending_orders[order.order_id] = order
        
        # Persist to disk
        team_dir = config.get_data_path(f"team/{order.team_id}")
        team_dir.mkdir(parents=True, exist_ok=True)
        orders_file = team_dir / "pending_orders.jsonl"
        
        try:
            with open(orders_file, "a", encoding="utf-8") as f:
                order_dict = order.model_dump()
                # Convert datetime and Decimal to JSON-serializable
                order_dict["created_at"] = order_dict["created_at"].isoformat()
                order_dict["updated_at"] = order_dict["updated_at"].isoformat()
                order_dict["quantity"] = str(order_dict["quantity"])
                order_dict["filled_qty"] = str(order_dict["filled_qty"])
                order_dict["requested_price"] = str(order_dict["requested_price"])
                if order_dict.get("limit_price"):
                    order_dict["limit_price"] = str(order_dict["limit_price"])
                if order_dict.get("filled_avg_price"):
                    order_dict["filled_avg_price"] = str(order_dict["filled_avg_price"])
                
                f.write(json.dumps(order_dict) + "\n")
                
            logger.debug(f"Stored pending order {order.order_id} for team {order.team_id}")
        except Exception as e:
            logger.error(f"Failed to store pending order: {e}")
    
    def get_open_orders(self, team_id: str) -> List[PendingOrder]:
        """
        Get all open orders for a team.
        
        Args:
            team_id: Team identifier
            
        Returns:
            List of pending orders that are still open
        """
        result = []
        for order in self.pending_orders.values():
            if order.team_id == team_id and order.status not in ("filled", "cancelled", "rejected", "expired"):
                result.append(order)
        
        return result
    
    def get_order_by_id(self, order_id: str) -> Optional[PendingOrder]:
        """Get a pending order by ID."""
        return self.pending_orders.get(order_id)
    
    def update_order_status(self, order_id: str, status_data: dict) -> Optional[PendingOrder]:
        """
        Update order status from broker data.
        
        Args:
            order_id: Order identifier
            status_data: Status data from broker (from getOrderById or getAllOrders)
            
        Returns:
            Updated PendingOrder or None if not found
        """
        order = self.pending_orders.get(order_id)
        if not order:
            return None
        
        # Update order fields
        order.status = status_data.get("status", order.status)
        order.updated_at = datetime.now(timezone.utc)
        
        if status_data.get("filled_qty"):
            order.filled_qty = Decimal(str(status_data["filled_qty"]))
        
        if status_data.get("filled_avg_price"):
            order.filled_avg_price = Decimal(str(status_data["filled_avg_price"]))
        
        logger.info(
            f"Updated order {order_id}: status={order.status}, filled={order.filled_qty}/{order.quantity}"
        )
        
        # If order is filled, create trade record
        if order.status == "filled" and order.filled_avg_price:
            self._create_trade_record_from_order(order)
            # Remove from pending
            del self.pending_orders[order_id]
        
        return order
    
    def _create_trade_record_from_order(self, order: PendingOrder) -> None:
        """
        Create a trade record from a filled order and append to trades.jsonl.
        
        Args:
            order: Filled PendingOrder
        """
        try:
            trade = TradeRecord(
                team_id=order.team_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                requested_price=order.requested_price,
                execution_price=order.filled_avg_price or order.requested_price,
                order_type=order.order_type,
                timestamp=order.updated_at,
                broker_order_id=order.broker_order_id,
            )
            
            # Append to trades file
            team_dir = config.get_data_path(f"team/{order.team_id}")
            trades_file = team_dir / "trades.jsonl"
            
            with open(trades_file, "a", encoding="utf-8") as f:
                trade_dict = trade.model_dump()
                trade_dict["timestamp"] = trade_dict["timestamp"].isoformat()
                trade_dict["quantity"] = str(trade_dict["quantity"])
                trade_dict["requested_price"] = str(trade_dict["requested_price"])
                trade_dict["execution_price"] = str(trade_dict["execution_price"])
                
                f.write(json.dumps(trade_dict) + "\n")
            
            logger.info(
                f"Created trade record for filled order {order.order_id}: "
                f"{order.side} {order.quantity} {order.symbol} @ {order.filled_avg_price}"
            )
        except Exception as e:
            logger.error(f"Failed to create trade record from order: {e}")
    
    def load_pending_orders(self) -> None:
        """
        Load all pending orders from disk on startup.
        """
        team_root = config.get_data_path("team")
        if not team_root.exists():
            return
        
        for team_dir in team_root.iterdir():
            if not team_dir.is_dir():
                continue
            
            orders_file = team_dir / "pending_orders.jsonl"
            if not orders_file.exists():
                continue
            
            try:
                with open(orders_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            order_dict = json.loads(line)
                            # Convert strings back to proper types
                            order_dict["quantity"] = Decimal(order_dict["quantity"])
                            order_dict["filled_qty"] = Decimal(order_dict["filled_qty"])
                            order_dict["requested_price"] = Decimal(order_dict["requested_price"])
                            if order_dict.get("limit_price"):
                                order_dict["limit_price"] = Decimal(order_dict["limit_price"])
                            if order_dict.get("filled_avg_price"):
                                order_dict["filled_avg_price"] = Decimal(order_dict["filled_avg_price"])
                            order_dict["created_at"] = datetime.fromisoformat(order_dict["created_at"])
                            order_dict["updated_at"] = datetime.fromisoformat(order_dict["updated_at"])
                            
                            order = PendingOrder(**order_dict)
                            
                            # Only load if not already filled/cancelled
                            if order.status not in ("filled", "cancelled", "rejected", "expired"):
                                self.pending_orders[order.order_id] = order
                        except Exception as e:
                            logger.warning(f"Failed to parse pending order: {e}")
            except Exception as e:
                logger.error(f"Failed to load pending orders from {orders_file}: {e}")
        
        logger.info(f"Loaded {len(self.pending_orders)} pending orders")
    
    async def reconcile_with_broker(self, broker) -> None:
        """
        Reconcile pending orders with broker (Alpaca).
        Updates execution prices and statuses.
        
        Args:
            broker: AlpacaBroker instance (or None if local-only)
        """
        if broker is None:
            return
        
        if not self.pending_orders:
            return
        
        logger.info(f"Reconciling {len(self.pending_orders)} pending orders with Alpaca...")
        
        updated_count = 0
        filled_count = 0
        
        for order_id, order in list(self.pending_orders.items()):
            try:
                # Query Alpaca for current order status
                broker_data = broker.getOrderById(order.broker_order_id)
                
                # Update order with latest data
                old_status = order.status
                updated_order = self.update_order_status(order_id, broker_data)
                
                if updated_order:
                    updated_count += 1
                    if updated_order.status == "filled" and old_status != "filled":
                        filled_count += 1
                        logger.info(
                            f"Order {order_id} FILLED: {order.symbol} @ "
                            f"{updated_order.filled_avg_price} (requested: {order.requested_price})"
                        )
            except Exception as e:
                logger.warning(f"Failed to reconcile order {order_id}: {e}")
        
        if updated_count > 0:
            logger.info(
                f"Reconciliation complete: {updated_count} orders updated, {filled_count} filled"
            )
    
    def cleanup_old_orders(self, max_age_days: int = 7) -> None:
        """
        Remove old filled/cancelled orders from memory.
        
        Args:
            max_age_days: Remove orders older than this many days
        """
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        removed = 0
        
        for order_id in list(self.pending_orders.keys()):
            order = self.pending_orders[order_id]
            if order.updated_at < cutoff and order.status in ("filled", "cancelled", "rejected", "expired"):
                del self.pending_orders[order_id]
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} old orders")


# Global instance
order_tracker = OrderTracker()

