"""
QTC Alpha API Server

Main FastAPI application that mounts all API routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.middleware import RequestIDMiddleware, get_rate_limit_key
from app.api.routers import health, activity, leaderboard, teams, market, system
from app.config.settings import DEFAULT_RATE_LIMIT


# =============================================================================
# Application Setup
# =============================================================================

app = FastAPI(
    title="QTC Alpha API",
    version="1.0",
    description="Quantitative Trading Competition API",
)

# Configure rate limiter (uses API key if present, falls back to IP)
limiter = Limiter(key_func=get_rate_limit_key, default_limits=[DEFAULT_RATE_LIMIT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enable simple, safe CORS so the frontend can fetch from browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Request ID and timing middleware
app.add_middleware(RequestIDMiddleware)


# =============================================================================
# Mount Routers
# =============================================================================

# Health checks (no prefix - /health/*)
app.include_router(health.router)

# Activity stream (prefix in router - /activity/*)
app.include_router(activity.router)

# Leaderboard (mixed - /leaderboard, /api/v1/leaderboard/*, /{team_key})
app.include_router(leaderboard.router)

# Team endpoints (prefix in router - /api/v1/team/*)
app.include_router(teams.router)

# Market data (prefix in router - /api/v1/market/*)
app.include_router(market.router)

# System status and admin (mixed - /api/v1/status, /api/v1/system/*)
app.include_router(system.router)
