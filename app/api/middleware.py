"""API middleware components for request processing and security."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request body size limits.
    
    Prevents memory exhaustion from large uploads by checking Content-Length
    header before reading the request body. Returns 413 Payload Too Large
    for oversized requests.
    """
    
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB for single files
    MAX_PACKAGE_SIZE = 50 * 1024 * 1024  # 50MB for ZIP packages
    
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and "upload" in request.url.path:
            content_length = request.headers.get("content-length")
            
            if content_length:
                content_length = int(content_length)
                
                if "upload-strategy-package" in request.url.path or "upload-multiple-files" in request.url.path:
                    max_size = self.MAX_PACKAGE_SIZE
                    max_size_mb = 50
                else:
                    max_size = self.MAX_UPLOAD_SIZE
                    max_size_mb = 10
                
                if content_length > max_size:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": f"Request body too large. Maximum allowed size is {max_size_mb}MB",
                            "status_code": 413,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "path": str(request.url.path),
                            "received_size_mb": round(content_length / (1024 * 1024), 2),
                            "max_size_mb": max_size_mb
                        }
                    )
        
        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Enforce request timeout limits to prevent hung connections."""
    
    STANDARD_TIMEOUT = 30
    UPLOAD_TIMEOUT = 60
    
    async def dispatch(self, request: Request, call_next):
        if "upload" in request.url.path:
            timeout = self.UPLOAD_TIMEOUT
        else:
            timeout = self.STANDARD_TIMEOUT
        
        try:
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "error": f"Request timeout after {timeout} seconds",
                    "status_code": 504,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "path": str(request.url.path),
                    "timeout_seconds": timeout
                }
            )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to each request for tracking and debugging."""
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        return response


class AuthFailureRateLimiter(BaseHTTPMiddleware):
    """Rate limit authentication failures to prevent brute-force attacks.
    
    Tracks 401 Unauthorized responses per IP address. After 5 failures
    within 60 seconds, blocks the IP for 5 minutes.
    """
    
    MAX_FAILURES = 5
    FAILURE_WINDOW = 60
    BLOCK_DURATION = 300
    
    def __init__(self, app):
        super().__init__(app)
        self._failures: Dict[str, List[float]] = defaultdict(list)
        self._blocked: Dict[str, float] = {}
    
    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def _clean_old_failures(self, ip: str, current_time: float):
        """Remove failures outside the tracking window."""
        cutoff = current_time - self.FAILURE_WINDOW
        self._failures[ip] = [t for t in self._failures[ip] if t > cutoff]
        if not self._failures[ip]:
            del self._failures[ip]
    
    def _is_blocked(self, ip: str, current_time: float) -> bool:
        """Check if IP is currently blocked."""
        if ip in self._blocked:
            if current_time < self._blocked[ip]:
                return True
            else:
                del self._blocked[ip]
        return False
    
    def _record_failure(self, ip: str, current_time: float):
        """Record an auth failure and block if threshold exceeded."""
        self._clean_old_failures(ip, current_time)
        self._failures[ip].append(current_time)
        
        if len(self._failures[ip]) >= self.MAX_FAILURES:
            self._blocked[ip] = current_time + self.BLOCK_DURATION
            del self._failures[ip]
    
    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        if self._is_blocked(client_ip, current_time):
            remaining = int(self._blocked[client_ip] - current_time)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many authentication failures. Please try again later.",
                    "status_code": 429,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "path": str(request.url.path),
                    "retry_after_seconds": remaining
                }
            )
        
        response = await call_next(request)
        
        if response.status_code == 401:
            self._record_failure(client_ip, current_time)
        
        return response
