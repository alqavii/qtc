"""
API Routers package.

Contains modular route handlers organized by domain.
"""

from app.api.routers import health, activity, leaderboard, teams, market, system

__all__ = ["health", "activity", "leaderboard", "teams", "market", "system"]
