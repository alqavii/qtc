"""
Health check endpoints for container orchestration and load balancers.
"""

import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.environments import config

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live")
def health_live():
    """
    Liveness probe - checks if the process is running.
    
    Returns 200 if the server can respond. Used by Kubernetes/Docker
    to determine if the container needs to be restarted.
    """
    return {"status": "alive"}


@router.get("/ready")
def health_ready():
    """
    Readiness probe - checks if the service can accept traffic.
    
    Checks:
    - Runtime status file exists (orchestrator has started)
    - Alpaca broker is configured (optional, degrades gracefully)
    
    Returns 200 if ready, 503 if not ready.
    """
    checks = {
        "orchestrator": False,
        "broker_configured": False,
    }
    
    # Check if orchestrator has written status
    status_file = config.get_data_path("runtime/status.json")
    if status_file.exists():
        checks["orchestrator"] = True
    
    # Check if broker credentials are available
    alpaca_key = os.getenv("ALPACA_KEY") or os.getenv("APCA_API_KEY_ID")
    alpaca_secret = os.getenv("ALPACA_SECRET") or os.getenv("APCA_API_SECRET_KEY")
    if alpaca_key and alpaca_secret:
        checks["broker_configured"] = True
    
    # Ready if orchestrator is running (broker is optional)
    is_ready = checks["orchestrator"]
    
    response = {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
    }
    
    if is_ready:
        return response
    else:
        return JSONResponse(status_code=503, content=response)
