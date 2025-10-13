#!/bin/bash
# Test script for strategy upload using curl

# Configuration
API_BASE="http://localhost:8000"
TEAM_ID="test1"

# Get API key from api_keys.json
API_KEY=$(jq -r ".${TEAM_ID}" ../data/api_keys.json 2>/dev/null)

if [ -z "$API_KEY" ] || [ "$API_KEY" = "null" ]; then
    echo "Error: Could not find API key for team ${TEAM_ID}"
    echo "Available teams:"
    jq -r 'keys[]' ../data/api_keys.json 2>/dev/null || echo "  (api_keys.json not found)"
    exit 1
fi

echo "Testing Strategy Upload API"
echo "Team: ${TEAM_ID}"
echo "API Key: ${API_KEY:0:20}..."
echo ""

# Test 1: Single file upload
echo "=== Test 1: Single File Upload ==="
curl -X POST "${API_BASE}/api/v1/team/${TEAM_ID}/upload-strategy" \
  -F "key=${API_KEY}" \
  -F "strategy_file=@strategy.py" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""

# Test 2: Create ZIP and upload
echo "=== Test 2: ZIP Package Upload ==="
echo "Creating ZIP package..."
cd multi_file
zip -q ../strategy_package.zip *.py
cd ..

curl -X POST "${API_BASE}/api/v1/team/${TEAM_ID}/upload-strategy-package" \
  -F "key=${API_KEY}" \
  -F "strategy_zip=@strategy_package.zip" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""

# Test 3: Multiple files upload
echo "=== Test 3: Multiple Files Upload ==="
curl -X POST "${API_BASE}/api/v1/team/${TEAM_ID}/upload-multiple-files" \
  -F "key=${API_KEY}" \
  -F "files=@multi_file/strategy.py" \
  -F "files=@multi_file/indicators.py" \
  -F "files=@multi_file/risk_manager.py" \
  -F "files=@multi_file/config.py" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat
echo ""

# Test 4: Invalid upload (should fail)
echo "=== Test 4: Invalid Upload (should fail) ==="
echo "import requests
class Strategy:
    def generate_signal(self, team, bars, current_prices):
        return None" > /tmp/invalid_strategy.py

curl -X POST "${API_BASE}/api/v1/team/${TEAM_ID}/upload-strategy" \
  -F "key=${API_KEY}" \
  -F "strategy_file=@/tmp/invalid_strategy.py" \
  -w "\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat

rm /tmp/invalid_strategy.py
echo ""

echo "=== All tests complete ==="

