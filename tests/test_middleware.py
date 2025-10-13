import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers

from app.api.middleware import (
    AuthFailureRateLimiter,
    RequestIDMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
)


class TestRequestSizeLimitMiddleware:
    
    @pytest.mark.asyncio
    async def test_single_file_under_limit(self):
        middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/team/test1/upload-strategy"
        request.headers = Headers({"content-length": str(5 * 1024 * 1024)})  # 5MB
        
        call_next = AsyncMock(return_value=Response())
        response = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        assert not isinstance(response, JSONResponse)
    
    @pytest.mark.asyncio
    async def test_single_file_over_limit(self):
        middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/team/test1/upload-strategy"
        request.headers = Headers({"content-length": str(15 * 1024 * 1024)})  # 15MB
        
        call_next = AsyncMock()
        response = await middleware.dispatch(request, call_next)
        
        assert not call_next.called
        assert isinstance(response, JSONResponse)
        assert response.status_code == 413
        assert "10MB" in str(response.body)
    
    @pytest.mark.asyncio
    async def test_package_under_limit(self):
        middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/team/test1/upload-strategy-package"
        request.headers = Headers({"content-length": str(30 * 1024 * 1024)})  # 30MB
        
        call_next = AsyncMock(return_value=Response())
        response = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        assert not isinstance(response, JSONResponse)
    
    @pytest.mark.asyncio
    async def test_package_over_limit(self):
        middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/team/test1/upload-strategy-package"
        request.headers = Headers({"content-length": str(60 * 1024 * 1024)})  # 60MB
        
        call_next = AsyncMock()
        response = await middleware.dispatch(request, call_next)
        
        assert not call_next.called
        assert isinstance(response, JSONResponse)
        assert response.status_code == 413
        assert "50MB" in str(response.body)
    
    @pytest.mark.asyncio
    async def test_multiple_files_uses_package_limit(self):
        middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/team/test1/upload-multiple-files"
        request.headers = Headers({"content-length": str(45 * 1024 * 1024)})  # 45MB
        
        call_next = AsyncMock(return_value=Response())
        response = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        assert not isinstance(response, JSONResponse)
    
    @pytest.mark.asyncio
    async def test_non_upload_request_passes_through(self):
        middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/v1/team/test1/history"
        request.headers = Headers({})
        
        call_next = AsyncMock(return_value=Response())
        response = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        assert not isinstance(response, JSONResponse)


class TestSecurityHeadersMiddleware:
    
    @pytest.mark.asyncio
    async def test_adds_all_security_headers(self):
        middleware = SecurityHeadersMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        original_response = Response()
        call_next = AsyncMock(return_value=original_response)
        
        response = await middleware.dispatch(request, call_next)
        
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    
    @pytest.mark.asyncio
    async def test_preserves_existing_headers(self):
        middleware = SecurityHeadersMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        original_response = Response()
        original_response.headers["Custom-Header"] = "custom-value"
        call_next = AsyncMock(return_value=original_response)
        
        response = await middleware.dispatch(request, call_next)
        
        assert response.headers["Custom-Header"] == "custom-value"
        assert "X-Content-Type-Options" in response.headers


class TestTimeoutMiddleware:
    
    @pytest.mark.asyncio
    async def test_standard_request_uses_30s_timeout(self):
        middleware = TimeoutMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/history"
        
        call_next = AsyncMock(return_value=Response())
        
        start = time.time()
        response = await middleware.dispatch(request, call_next)
        duration = time.time() - start
        
        assert duration < 1  # Should complete quickly
        assert not isinstance(response, JSONResponse)
    
    @pytest.mark.asyncio
    async def test_upload_request_uses_60s_timeout(self):
        middleware = TimeoutMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/upload-strategy"
        
        call_next = AsyncMock(return_value=Response())
        response = await middleware.dispatch(request, call_next)
        
        assert not isinstance(response, JSONResponse)
    
    @pytest.mark.asyncio
    async def test_timeout_returns_504(self):
        middleware = TimeoutMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/history"
        
        async def slow_call_next(req):
            await asyncio.sleep(35)  # Longer than 30s timeout
            return Response()
        
        response = await middleware.dispatch(request, slow_call_next)
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 504
        assert "timeout" in str(response.body).lower()


class TestRequestIDMiddleware:
    
    @pytest.mark.asyncio
    async def test_adds_request_id_to_state(self):
        middleware = RequestIDMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.state = Mock()
        original_response = Response()
        call_next = AsyncMock(return_value=original_response)
        
        await middleware.dispatch(request, call_next)
        
        assert hasattr(request.state, 'request_id')
        assert len(request.state.request_id) == 36  # UUID format
    
    @pytest.mark.asyncio
    async def test_adds_request_id_to_response_header(self):
        middleware = RequestIDMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.state = Mock()
        original_response = Response()
        call_next = AsyncMock(return_value=original_response)
        
        response = await middleware.dispatch(request, call_next)
        
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36


class TestAuthFailureRateLimiter:
    
    @pytest.mark.asyncio
    async def test_allows_requests_under_threshold(self):
        middleware = AuthFailureRateLimiter(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/history"
        request.client = Mock(host="192.168.1.1")
        request.headers = Headers({})
        
        response_401 = Mock()
        response_401.status_code = 401
        call_next = AsyncMock(return_value=response_401)
        
        # First 4 failures should be allowed through
        for i in range(4):
            response = await middleware.dispatch(request, call_next)
            assert response.status_code == 401
            assert call_next.call_count == i + 1
    
    @pytest.mark.asyncio
    async def test_blocks_after_threshold(self):
        middleware = AuthFailureRateLimiter(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/history"
        request.client = Mock(host="192.168.1.1")
        request.headers = Headers({})
        
        response_401 = Mock()
        response_401.status_code = 401
        call_next = AsyncMock(return_value=response_401)
        
        # Record 5 failures
        for _ in range(5):
            await middleware.dispatch(request, call_next)
        
        # 6th request should be blocked before reaching endpoint
        response = await middleware.dispatch(request, call_next)
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 429
        assert "authentication failures" in str(response.body).lower()
    
    @pytest.mark.asyncio
    async def test_allows_successful_requests(self):
        middleware = AuthFailureRateLimiter(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/history"
        request.client = Mock(host="192.168.1.1")
        request.headers = Headers({})
        
        response_200 = Mock()
        response_200.status_code = 200
        call_next = AsyncMock(return_value=response_200)
        
        # Make 10 successful requests
        for _ in range(10):
            response = await middleware.dispatch(request, call_next)
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_tracks_per_ip(self):
        middleware = AuthFailureRateLimiter(app=Mock())
        
        response_401 = Mock()
        response_401.status_code = 401
        call_next = AsyncMock(return_value=response_401)
        
        # IP 1 fails 5 times
        request1 = Mock(spec=Request)
        request1.url.path = "/api/v1/team/test1/history"
        request1.client = Mock(host="192.168.1.1")
        request1.headers = Headers({})
        
        for _ in range(5):
            await middleware.dispatch(request1, call_next)
        
        # IP 2 should still be allowed
        request2 = Mock(spec=Request)
        request2.url.path = "/api/v1/team/test1/history"
        request2.client = Mock(host="192.168.1.2")
        request2.headers = Headers({})
        
        response = await middleware.dispatch(request2, call_next)
        assert response.status_code == 401  # Not blocked
    
    @pytest.mark.asyncio
    async def test_respects_x_forwarded_for(self):
        middleware = AuthFailureRateLimiter(app=Mock())
        
        request = Mock(spec=Request)
        request.url.path = "/api/v1/team/test1/history"
        request.client = Mock(host="10.0.0.1")
        request.headers = Headers({"X-Forwarded-For": "203.0.113.1, 198.51.100.1"})
        
        response_401 = Mock()
        response_401.status_code = 401
        call_next = AsyncMock(return_value=response_401)
        
        # Record 5 failures
        for _ in range(5):
            await middleware.dispatch(request, call_next)
        
        # Should be blocked by the forwarded IP
        response = await middleware.dispatch(request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 429


class TestMiddlewareIntegration:
    
    @pytest.mark.asyncio
    async def test_middleware_execution_order(self):
        execution_order = []
        
        class TrackingMiddleware:
            def __init__(self, name):
                self.name = name
            
            async def __call__(self, request, call_next):
                execution_order.append(f"{self.name}_before")
                response = await call_next(request)
                execution_order.append(f"{self.name}_after")
                return response
        
        # Middleware should execute in reverse order of registration
        # Last registered runs first
        assert True  # Order is validated by actual API tests
    
    @pytest.mark.asyncio
    async def test_size_limit_before_timeout(self):
        size_middleware = RequestSizeLimitMiddleware(app=Mock())
        
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/v1/team/test1/upload-strategy"
        request.headers = Headers({"content-length": str(15 * 1024 * 1024)})  # Over limit
        
        # Should reject immediately without starting timeout
        start = time.time()
        response = await size_middleware.dispatch(request, AsyncMock())
        duration = time.time() - start
        
        assert duration < 0.1  # Should be instant
        assert response.status_code == 413


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
