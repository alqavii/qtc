#!/usr/bin/env python3
"""
Test script for strategy upload endpoints.
This demonstrates how to upload strategies via the API.
"""

import requests
import zipfile
import io
from pathlib import Path

# API configuration
API_BASE = "http://localhost:8000"
TEAM_ID = "test1"

# Get API key from data/api_keys.json
import json
api_keys_path = Path(__file__).parents[1] / "data" / "api_keys.json"
if api_keys_path.exists():
    with open(api_keys_path) as f:
        keys = json.load(f)
        API_KEY = keys.get(TEAM_ID)
        if not API_KEY:
            print(f"Error: No API key found for team {TEAM_ID}")
            print(f"Available teams: {', '.join(keys.keys())}")
            exit(1)
else:
    print(f"Error: API keys file not found at {api_keys_path}")
    print("Please ensure the API server has generated keys")
    exit(1)


def test_single_file_upload():
    """Test uploading a single strategy.py file"""
    print("\n=== Testing Single File Upload ===")
    
    strategy_file = Path(__file__).parent / "strategy.py"
    
    if not strategy_file.exists():
        print(f"Error: {strategy_file} not found")
        return
    
    with open(strategy_file, 'rb') as f:
        files = {'strategy_file': f}
        data = {'key': API_KEY}
        
        response = requests.post(
            f"{API_BASE}/api/v1/team/{TEAM_ID}/upload-strategy",
            files=files,
            data=data
        )
    
    if response.ok:
        result = response.json()
        print(f"✓ Success: {result['message']}")
        print(f"  Files uploaded: {result['files_uploaded']}")
        print(f"  Path: {result['path']}")
    else:
        print(f"✗ Error: {response.status_code}")
        print(f"  {response.json()}")


def test_zip_upload():
    """Test uploading a ZIP package with multiple files"""
    print("\n=== Testing ZIP Package Upload ===")
    
    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    multi_file_dir = Path(__file__).parent / "multi_file"
    
    if not multi_file_dir.exists():
        print(f"Error: {multi_file_dir} not found")
        return
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for py_file in multi_file_dir.glob("*.py"):
            zf.write(py_file, py_file.name)
    
    zip_buffer.seek(0)
    
    files = {'strategy_zip': ('strategy_package.zip', zip_buffer, 'application/zip')}
    data = {'key': API_KEY}
    
    response = requests.post(
        f"{API_BASE}/api/v1/team/{TEAM_ID}/upload-strategy-package",
        files=files,
        data=data
    )
    
    if response.ok:
        result = response.json()
        print(f"✓ Success: {result['message']}")
        print(f"  Files uploaded: {result['files_uploaded']}")
        print(f"  File count: {result['file_count']}")
        print(f"  Path: {result['path']}")
        print(f"  Validation: {result['validation']}")
    else:
        print(f"✗ Error: {response.status_code}")
        print(f"  {response.json()}")


def test_multiple_files_upload():
    """Test uploading multiple individual files"""
    print("\n=== Testing Multiple Files Upload ===")
    
    multi_file_dir = Path(__file__).parent / "multi_file"
    
    if not multi_file_dir.exists():
        print(f"Error: {multi_file_dir} not found")
        return
    
    # Prepare files
    files_to_upload = []
    for py_file in multi_file_dir.glob("*.py"):
        files_to_upload.append(
            ('files', (py_file.name, open(py_file, 'rb'), 'text/x-python'))
        )
    
    data = {'key': API_KEY}
    
    response = requests.post(
        f"{API_BASE}/api/v1/team/{TEAM_ID}/upload-multiple-files",
        files=files_to_upload,
        data=data
    )
    
    # Close file handles
    for _, (_, fh, _) in files_to_upload:
        fh.close()
    
    if response.ok:
        result = response.json()
        print(f"✓ Success: {result['message']}")
        print(f"  Files uploaded: {result['files_uploaded']}")
        print(f"  File count: {result['file_count']}")
        print(f"  Path: {result['path']}")
    else:
        print(f"✗ Error: {response.status_code}")
        print(f"  {response.json()}")


def test_invalid_upload():
    """Test that invalid uploads are rejected"""
    print("\n=== Testing Invalid Upload (should fail) ===")
    
    # Create a file with disallowed import
    invalid_code = """
import requests  # NOT ALLOWED

class Strategy:
    def generate_signal(self, team, bars, current_prices):
        # This should be blocked by security validation
        return None
"""
    
    files = {'strategy_file': ('strategy.py', invalid_code.encode())}
    data = {'key': API_KEY}
    
    response = requests.post(
        f"{API_BASE}/api/v1/team/{TEAM_ID}/upload-strategy",
        files=files,
        data=data
    )
    
    if not response.ok:
        print(f"✓ Correctly rejected: {response.status_code}")
        print(f"  Reason: {response.json().get('detail')}")
    else:
        print(f"✗ Error: Invalid upload was accepted (should have been rejected)")


if __name__ == "__main__":
    print(f"Testing strategy upload endpoints for team: {TEAM_ID}")
    print(f"API Base: {API_BASE}")
    print(f"API Key: {API_KEY[:20]}...")
    
    # Run tests
    test_single_file_upload()
    test_zip_upload()
    test_multiple_files_upload()
    test_invalid_upload()
    
    print("\n=== All Tests Complete ===")

