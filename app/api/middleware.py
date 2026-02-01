"""
API Middleware components.

Provides request-level utilities like request ID tracking.
"""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique request ID to each incoming request.
    
    - Generates a UUID for each request
    - Stores it in request.state.request_id for use in handlers
    - Adds X-Request-ID header to response
    - Logs request method, path, status, and duration
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Store in request state for access in route handlers
        request.state.request_id = request_id
        
        # Track timing
        start_time = time.perf_counter()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Add headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        
        # Log the request (skip health checks to reduce noise)
        path = request.url.path
        if not path.startswith("/health"):
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration=%.2fms",
                request_id,
                request.method,
                path,
                response.status_code,
                duration_ms,
            )
        
        return response


def get_request_id(request: Request) -> str:
    """
    Helper to retrieve request ID from request state.
    
    Returns 'unknown' if middleware hasn't run (shouldn't happen in normal flow).
    """
    return getattr(request.state, "request_id", "unknown")
