#!/usr/bin/env python3
"""
Quick test script for the new metrics API endpoints.
Run this after starting the API server to verify endpoints work.
"""

import requests
import json
from typing import Dict, Any

API_BASE = "http://localhost:8000"

def test_endpoint(name: str, url: str, expected_keys: list) -> bool:
    """Test an API endpoint and verify response structure."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status: 200 OK")
            print(f"✅ Response received")
            
            # Check for expected keys
            missing_keys = [key for key in expected_keys if key not in data]
            if missing_keys:
                print(f"⚠️  Missing keys: {missing_keys}")
            else:
                print(f"✅ All expected keys present")
            
            # Pretty print sample data
            print(f"\nSample response:")
            print(json.dumps(data, indent=2, default=str)[:500] + "...")
            
            return True
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection Error: Is the API server running?")
        print(f"   Start with: uvicorn app.api.server:app --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("QTC Alpha API - Metrics Endpoints Test")
    print("=" * 60)
    
    results = []
    
    # Test 1: Original leaderboard (should still work)
    results.append(test_endpoint(
        "Original Leaderboard",
        f"{API_BASE}/leaderboard",
        ["leaderboard"]
    ))
    
    # Test 2: Leaderboard with metrics (no auth required)
    results.append(test_endpoint(
        "Leaderboard with Metrics",
        f"{API_BASE}/api/v1/leaderboard/metrics?days=7&sort_by=portfolio_value",
        ["leaderboard", "sort_by", "calculation_period_days"]
    ))
    
    # Test 3: Leaderboard sorted by Sharpe ratio
    results.append(test_endpoint(
        "Leaderboard Sorted by Sharpe Ratio",
        f"{API_BASE}/api/v1/leaderboard/metrics?sort_by=sharpe_ratio",
        ["leaderboard", "sort_by"]
    ))
    
    # Test 4: Historical data endpoint
    results.append(test_endpoint(
        "Leaderboard History",
        f"{API_BASE}/api/v1/leaderboard/history?days=7&limit=100",
        ["days", "teams"]
    ))
    
    # Note: Team-specific endpoints require API key
    print(f"\n{'='*60}")
    print("Note: Team-specific endpoints require authentication")
    print("To test:")
    print(f"  curl \"{API_BASE}/api/v1/team/YOUR_TEAM_ID/metrics?key=YOUR_API_KEY\"")
    print(f"{'='*60}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    total = len(results)
    passed = sum(results)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All tests passed!")
    else:
        print(f"⚠️  {total - passed} test(s) failed")
    
    print(f"\nAPI Documentation: {API_BASE}/docs")
    print(f"ReDoc: {API_BASE}/redoc")


if __name__ == "__main__":
    main()

