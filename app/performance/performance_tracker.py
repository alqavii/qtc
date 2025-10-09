from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from app.models.teams import Team
import logging

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Comprehensive performance tracking and reporting system"""

    def __init__(self, data_dir: str = "data/performance"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Performance data storage
        self.portfolio_history: Dict[str, List[Dict]] = {}
        self.trade_history: Dict[str, List[Dict]] = {}
        self.performance_metrics: Dict[str, Dict] = {}
        self.benchmark_data: Dict[str, List[float]] = {}

        # Performance calculation parameters
        self.benchmark_symbol = "SPY"

    def update_portfolio_snapshot(
        self,
        team: Team,
        current_prices: Dict[str, Decimal],
        *,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Update portfolio snapshot for performance tracking"""
        team_id = str(team.teamId)
        ts = timestamp or datetime.now(timezone.utc)

        # Calculate portfolio value
        portfolio_value = team.portfolio.marketValue(current_prices)

        # Calculate position values
        position_values = {}
        for symbol, position in team.portfolio.positions.items():
            if symbol in current_prices:
                position_values[symbol] = {
                    "quantity": float(position.quantity),
                    "price": float(current_prices[symbol]),
                    "value": float(position.quantity * current_prices[symbol]),
                    "side": position.side,
                    "avg_cost": float(position.avgCost),
                    "unrealized_pnl": float(
                        (current_prices[symbol] - position.avgCost) * position.quantity
                    ),
                }

        # Create snapshot
        snapshot = {
            "timestamp": ts,
            "portfolio_value": float(portfolio_value),
            "cash": float(team.portfolio.freeCash),
            "positions": position_values,
            "position_count": len(team.portfolio.positions),
            "gross_exposure": float(team.portfolio.grossExposure(current_prices)),
            "net_exposure": float(team.portfolio.netExposure(current_prices)),
        }

        # Store snapshot
        if team_id not in self.portfolio_history:
            self.portfolio_history[team_id] = []

        self.portfolio_history[team_id].append(snapshot)

    def update_trade_record(self, team_id: str, trade_record: Dict) -> None:
        """Update trade record for performance tracking"""
        if team_id not in self.trade_history:
            self.trade_history[team_id] = []

        self.trade_history[team_id].append(trade_record)

    def calculate_performance_metrics(self, team_id: str) -> Dict[str, Any]:
        """Calculate performance metrics for a team."""
        history = self.portfolio_history.get(team_id)
        if not history or len(history) < 2:
            return {"error": "Insufficient data for performance calculation"}

        try:
            portfolio_data = history
            trade_data = self.trade_history.get(team_id, [])

            values = [snapshot["portfolio_value"] for snapshot in portfolio_data]
            timestamps = [snapshot["timestamp"] for snapshot in portfolio_data]

            returns = [
                (values[i] - values[i - 1]) / values[i - 1]
                for i in range(1, len(values))
                if values[i - 1] > 0
            ]
            if not returns:
                return {"error": "No valid returns calculated"}

            total_return = (values[-1] - values[0]) / values[0] if values[0] > 0 else 0
            annualized_return = self._annualize_return(returns, timestamps)
            benchmark_return = self._calculate_benchmark_return(timestamps)
            trade_stats = self._calculate_trade_statistics(trade_data)

            metrics = {
                "team_id": team_id,
                "calculation_time": datetime.now(timezone.utc).isoformat(),
                "period": {
                    "start": timestamps[0].isoformat(),
                    "end": timestamps[-1].isoformat(),
                    "duration_days": (timestamps[-1] - timestamps[0]).total_seconds()
                    / 86400,
                },
                "returns": {
                    "total_return": total_return,
                    "annualized_return": annualized_return,
                    "benchmark_return": benchmark_return,
                },
                "portfolio": {
                    "initial_value": values[0],
                    "final_value": values[-1],
                    "peak_value": max(values),
                    "trough_value": min(values),
                    "current_cash_ratio": portfolio_data[-1].get("cash", 0) / values[-1]
                    if values[-1] > 0
                    else 0,
                },
                "trades": trade_stats,
            }

            self.performance_metrics[team_id] = metrics
            return metrics

        except Exception as e:
            logger.error(
                "Error calculating performance metrics for team %s: %s", team_id, e
            )
            return {"error": f"Performance calculation failed: {str(e)}"}

    def _annualize_return(
        self, returns: List[float], timestamps: List[datetime]
    ) -> float:
        """Calculate annualized return from returns and timestamps"""
        if not returns or not timestamps:
            return 0.0

        # Calculate time period in years
        time_span = (
            timestamps[-1] - timestamps[0]
        ).total_seconds() / 31536000  # seconds in a year

        if time_span <= 0:
            return 0.0

        # Calculate total return
        total_return = 1.0
        for ret in returns:
            total_return *= 1 + ret

        # Annualize
        annualized_return = (total_return ** (1 / time_span)) - 1
        return annualized_return

    def _calculate_trade_statistics(self, trade_data: List[Dict]) -> Dict[str, Any]:
        """Calculate trade statistics"""
        if not trade_data:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_trade_return": 0.0,
                "profit_factor": 0.0,
            }

        # Group trades by symbol and calculate P&L
        symbol_trades = {}
        for trade in trade_data:
            symbol = trade.get("symbol", "unknown")
            if symbol not in symbol_trades:
                symbol_trades[symbol] = []
            symbol_trades[symbol].append(trade)

        # Calculate basic statistics
        total_trades = len(trade_data)
        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0
        total_loss = 0.0

        # This is simplified - in practice, you'd track actual P&L per trade
        for symbol, trades in symbol_trades.items():
            # Simplified P&L calculation
            buy_trades = [t for t in trades if t.get("side") == "buy"]
            sell_trades = [t for t in trades if t.get("side") == "sell"]

            # Match buy/sell pairs (simplified)
            for i in range(min(len(buy_trades), len(sell_trades))):
                buy_price = buy_trades[i].get("price", 0)
                sell_price = sell_trades[i].get("price", 0)

                if buy_price > 0 and sell_price > 0:
                    pnl = sell_price - buy_price
                    if pnl > 0:
                        winning_trades += 1
                        total_profit += pnl
                    else:
                        losing_trades += 1
                        total_loss += abs(pnl)

        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        avg_trade_return = (
            (total_profit - total_loss) / total_trades if total_trades > 0 else 0.0
        )
        profit_factor = (
            total_profit / total_loss
            if total_loss > 0
            else float("inf")
            if total_profit > 0
            else 0.0
        )

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_trade_return": avg_trade_return,
            "total_profit": total_profit,
            "total_loss": total_loss,
            "profit_factor": profit_factor,
        }

    def _calculate_benchmark_return(self, timestamps: List[datetime]) -> float:
        """Calculate benchmark return for the same period (simplified)"""
        # In practice, you would fetch actual benchmark data
        # For now, return a placeholder
        return 0.08  # 8% annual return placeholder

    def generate_performance_report(self, team_id: str) -> Dict[str, Any]:
        """Generate comprehensive performance report for a team"""
        metrics = self.calculate_performance_metrics(team_id)

        if "error" in metrics:
            return metrics

        # Add additional analysis
        report = {
            **metrics,
            "analysis": self._analyze_performance(metrics),
            "recommendations": self._generate_recommendations(metrics),
        }

        return report

    def _analyze_performance(self, metrics: Dict[str, Any]) -> Dict[str, str]:
        analysis: Dict[str, str] = {}

        returns = metrics.get("returns", {})
        trades = metrics.get("trades", {})

        total_return = returns.get("total_return", 0)
        if total_return > 0.1:
            analysis["return_quality"] = "Excellent performance"
        elif total_return > 0.05:
            analysis["return_quality"] = "Good performance"
        elif total_return > 0:
            analysis["return_quality"] = "Positive but modest performance"
        else:
            analysis["return_quality"] = "Negative performance - review strategy"

        win_rate = trades.get("win_rate", 0)
        if win_rate > 0.6:
            analysis["trading_quality"] = "High win rate - strategy working well"
        elif win_rate > 0.4:
            analysis["trading_quality"] = "Moderate win rate - room for improvement"
        else:
            analysis["trading_quality"] = "Low win rate - strategy needs review"

        return analysis

    def _generate_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []

        returns = metrics.get("returns", {})
        trades = metrics.get("trades", {})

        # Return-based recommendations
        total_return = returns.get("total_return", 0)
        if total_return < 0:
            recommendations.append(
                "Consider reviewing strategy parameters or switching strategies"
            )

        # Trading recommendations
        win_rate = trades.get("win_rate", 0)
        if win_rate < 0.4:
            recommendations.append(
                "Review trade selection criteria to improve win rate"
            )

        return recommendations

    def save_performance_data(self, team_id: str) -> None:
        """Save performance data to disk"""
        try:
            # Save portfolio history
            if team_id in self.portfolio_history:
                portfolio_file = self.data_dir / f"{team_id}_portfolio_history.json"
                with open(portfolio_file, "w") as f:
                    json.dump(self.portfolio_history[team_id], f, default=str, indent=2)

            # Save trade history
            if team_id in self.trade_history:
                trade_file = self.data_dir / f"{team_id}_trade_history.json"
                with open(trade_file, "w") as f:
                    json.dump(self.trade_history[team_id], f, default=str, indent=2)

            # Save performance metrics
            if team_id in self.performance_metrics:
                metrics_file = self.data_dir / f"{team_id}_performance_metrics.json"
                with open(metrics_file, "w") as f:
                    json.dump(
                        self.performance_metrics[team_id], f, default=str, indent=2
                    )

            logger.info(f"Performance data saved for team {team_id}")

        except Exception as e:
            logger.error(f"Error saving performance data for team {team_id}: {str(e)}")

    def load_performance_data(self, team_id: str) -> bool:
        """Load performance data from disk"""
        try:
            # Load portfolio history
            portfolio_file = self.data_dir / f"{team_id}_portfolio_history.json"
            if portfolio_file.exists():
                with open(portfolio_file, "r") as f:
                    self.portfolio_history[team_id] = json.load(f)

            # Load trade history
            trade_file = self.data_dir / f"{team_id}_trade_history.json"
            if trade_file.exists():
                with open(trade_file, "r") as f:
                    self.trade_history[team_id] = json.load(f)

            # Load performance metrics
            metrics_file = self.data_dir / f"{team_id}_performance_metrics.json"
            if metrics_file.exists():
                with open(metrics_file, "r") as f:
                    self.performance_metrics[team_id] = json.load(f)

            logger.info(f"Performance data loaded for team {team_id}")
            return True

        except Exception as e:
            logger.error(f"Error loading performance data for team {team_id}: {str(e)}")
            return False


# Global performance tracker instance
performance_tracker = PerformanceTracker()
