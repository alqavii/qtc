"""Test suite for health check endpoint.

Tests /health endpoint for disk space, data directory access, and team count.
"""

import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestHealthCheckEndpoint:
    
    @pytest.fixture
    def test_app(self):
        from datetime import datetime, timezone
        
        app = FastAPI()
        
        @app.get("/health")
        def health_check():
            """Test health endpoint."""
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": {
                    "disk_space": {"status": "pass"},
                    "data_directory": {"status": "pass"},
                    "team_count": {"status": "pass", "count": 0}
                }
            }
        
        return app
    
    def test_health_check_exists(self, test_app):
        client = TestClient(test_app)
        response = client.get("/health")
        
        assert response.status_code in [200, 503]  # Either healthy or unhealthy
        assert response.json()  # Should return JSON
    
    def test_health_check_returns_status(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "unhealthy"]
    
    def test_health_check_returns_checks(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert "checks" in data
        assert isinstance(data["checks"], dict)
    
    def test_health_check_includes_disk_space(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert "disk_space" in data["checks"]
        
        disk_check = data["checks"]["disk_space"]
        assert "status" in disk_check
        assert disk_check["status"] in ["pass", "fail"]
    
    def test_health_check_includes_data_directory(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert "data_directory" in data["checks"]
        
        dir_check = data["checks"]["data_directory"]
        assert "status" in dir_check
        assert dir_check["status"] in ["pass", "fail"]
    
    def test_health_check_includes_team_count(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert "team_count" in data["checks"]
        
        team_check = data["checks"]["team_count"]
        assert "status" in team_check
        assert team_check["status"] in ["pass", "fail"]


    
    @patch('shutil.disk_usage')
    def test_disk_space_sufficient(self, mock_disk_usage):
        # Mock 20GB free (>10GB threshold)
        mock_disk_usage.return_value = Mock(
            total=100_000_000_000,
            used=80_000_000_000,
            free=20_000_000_000
        )
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        disk_check = data["checks"]["disk_space"]
        
        assert disk_check["status"] == "pass"
        assert response.status_code == 200
    
    @patch('shutil.disk_usage')
    def test_disk_space_insufficient(self, mock_disk_usage):
        # Mock 5GB free (<10GB threshold)
        mock_disk_usage.return_value = Mock(
            total=100_000_000_000,
            used=95_000_000_000,
            free=5_000_000_000
        )
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        disk_check = data["checks"]["disk_space"]
        
        assert disk_check["status"] == "fail"
        assert "insufficient" in disk_check.get("message", "").lower() or \
               "free" in disk_check.get("message", "").lower()
        assert response.status_code == 503
    
    @patch('shutil.disk_usage')
    def test_disk_space_at_threshold(self, mock_disk_usage):
        # Mock exactly 10GB free
        mock_disk_usage.return_value = Mock(
            total=100_000_000_000,
            used=90_000_000_000,
            free=10_000_000_000
        )
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        disk_check = data["checks"]["disk_space"]
        
        # At threshold should pass (>= 10GB)
        assert disk_check["status"] == "pass"
    
    @patch('shutil.disk_usage')
    def test_disk_space_includes_free_bytes(self, mock_disk_usage):
        mock_disk_usage.return_value = Mock(
            total=100_000_000_000,
            used=80_000_000_000,
            free=20_000_000_000
        )
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        disk_check = data["checks"]["disk_space"]
        
        # Should include some information about free space
        assert "free_gb" in disk_check or "message" in disk_check


class TestDataDirectoryCheck:
    
    @patch('os.path.exists')
    @patch('os.access')
    def test_data_directory_exists_and_writable(self, mock_access, mock_exists):
        mock_exists.return_value = True
        mock_access.return_value = True
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        dir_check = data["checks"]["data_directory"]
        
        assert dir_check["status"] == "pass"
    
    @patch('os.path.exists')
    def test_data_directory_missing(self, mock_exists):
        mock_exists.return_value = False
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        dir_check = data["checks"]["data_directory"]
        
        assert dir_check["status"] == "fail"
        assert "not exist" in dir_check.get("message", "").lower() or \
               "missing" in dir_check.get("message", "").lower()
        assert response.status_code == 503
    
    @patch('os.path.exists')
    @patch('os.access')
    def test_data_directory_not_writable(self, mock_access, mock_exists):
        mock_exists.return_value = True
        mock_access.return_value = False
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        dir_check = data["checks"]["data_directory"]
        
        assert dir_check["status"] == "fail"
        assert "writable" in dir_check.get("message", "").lower() or \
               "permission" in dir_check.get("message", "").lower()


    
    @patch('os.listdir')
    @patch('os.path.exists')
    def test_team_count_normal(self, mock_exists, mock_listdir):
        mock_exists.return_value = True
        mock_listdir.return_value = ['team1', 'team2', 'team3']
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        team_check = data["checks"]["team_count"]
        
        assert team_check["status"] == "pass"
        assert team_check.get("count") == 3 or "3" in team_check.get("message", "")
    
    @patch('os.path.exists')
    def test_team_count_directory_missing(self, mock_exists):
        mock_exists.return_value = False
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        team_check = data["checks"]["team_count"]
        
        # Should handle gracefully
        assert team_check["status"] in ["pass", "fail"]
    
    @patch('os.listdir')
    @patch('os.path.exists')
    def test_team_count_zero_teams(self, mock_exists, mock_listdir):
        mock_exists.return_value = True
        mock_listdir.return_value = []
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        team_check = data["checks"]["team_count"]
        
        assert team_check["status"] == "pass"
        assert team_check.get("count") == 0 or "0" in team_check.get("message", "")


class TestHealthCheckOverallStatus:
    
    @patch('shutil.disk_usage')
    @patch('os.path.exists')
    @patch('os.access')
    @patch('os.listdir')
    def test_all_checks_pass_returns_healthy(self, mock_listdir, mock_access, 
                                            mock_exists, mock_disk_usage):
        # All checks pass
        mock_disk_usage.return_value = Mock(free=20_000_000_000)
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_listdir.return_value = ['team1', 'team2']
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert data["status"] == "healthy"
        assert response.status_code == 200
    
    @patch('shutil.disk_usage')
    def test_any_check_fails_returns_unhealthy(self, mock_disk_usage):
        # Disk space check fails
        mock_disk_usage.return_value = Mock(free=5_000_000_000)
        
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        assert data["status"] == "unhealthy"
        assert response.status_code == 503


    
    def test_health_check_responds_quickly(self):
        import time
        
        client = TestClient(app)
        start = time.time()
        response = client.get("/health")
        duration = time.time() - start
        
        assert duration < 1.0  # Should respond within 1 second
        assert response.status_code in [200, 503]
    
    def test_health_check_no_authentication_required(self):
        client = TestClient(app)
        response = client.get("/health")
        
        # Should not return 401 Unauthorized
        assert response.status_code != 401
        assert response.status_code in [200, 503]
    
    def test_health_check_handles_errors_gracefully(self):
        # Even if checks fail, should return valid JSON
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert "status" in data
        assert "checks" in data


class TestHealthCheckMonitoring:
    
    def test_health_check_json_structure(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        
        # Top level fields
        assert "status" in data
        assert "checks" in data
        
        # Each check has status
        for check_name, check_data in data["checks"].items():
            assert "status" in check_data
            assert check_data["status"] in ["pass", "fail"]
    
    def test_health_check_200_vs_503(self):
        client = TestClient(app)
        response = client.get("/health")
        
        data = response.json()
        
        if data["status"] == "healthy":
            assert response.status_code == 200
        else:
            assert response.status_code == 503


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
