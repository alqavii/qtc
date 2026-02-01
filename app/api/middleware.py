"""
API Middleware components.

Provides request-level utilities like request ID tracking and rate limiting.
"""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """
    Extract rate limiting key from request.
    
    Priority:
    1. API key from query parameter 'key'
    2. API key from Authorization header (Bearer token)
    3. Fall back to remote IP address
    
    This allows per-key rate limiting for authenticated requests,
    while still protecting against unauthenticated abuse by IP.
    """
    # Try query parameter first (most common in this API)
    key = request.query_params.get("key")
    if key:
        return f"key:{key[:16]}"  # Use prefix to avoid logging full key
    
    # Try Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return f"key:{token[:16]}"
    
    # Fall back to IP address
    return f"ip:{get_remote_address(request)}"


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
