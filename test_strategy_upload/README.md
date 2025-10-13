# Strategy Upload API - Test & Documentation

This directory contains test files and examples for the strategy upload functionality.

## Overview

The QTC Alpha platform now supports **uploading strategies via API** instead of using GitHub. This allows teams to submit their trading strategies through a web interface or programmatically.

## Available Endpoints

### 1. Single File Upload
**Endpoint:** `POST /api/v1/team/{team_id}/upload-strategy`

Upload a single `strategy.py` file for simple strategies.

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/team/test1/upload-strategy" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_file=@strategy.py"
```

### 2. ZIP Package Upload (Recommended for Multi-File)
**Endpoint:** `POST /api/v1/team/{team_id}/upload-strategy-package`

Upload a ZIP file containing `strategy.py` and helper modules.

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/team/test1/upload-strategy-package" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_zip=@strategy_package.zip"
```

### 3. Multiple Files Upload
**Endpoint:** `POST /api/v1/team/{team_id}/upload-multiple-files`

Upload multiple Python files individually.

**Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/team/test1/upload-multiple-files" \
  -F "key=YOUR_API_KEY" \
  -F "files=@strategy.py" \
  -F "files=@indicators.py" \
  -F "files=@utils.py"
```

## File Structure Examples

### Simple Strategy (Single File)
```
strategy.py          # Main entry point with Strategy class
```

### Complex Strategy (Multi-File)
```
strategy_package.zip
├── strategy.py          # Required entry point
├── indicators.py        # Technical indicators
├── risk_manager.py      # Risk management
└── config.py            # Configuration constants
```

## Security Validation

All uploaded files are validated for security:

✅ **Allowed:**
- `numpy`, `pandas`, `scipy` - Data processing
- `math`, `statistics`, `decimal` - Math operations
- `collections`, `typing` - Standard library

❌ **Blocked:**
- `requests`, `urllib`, `socket` - Network access
- `open()`, file I/O - File system access
- `subprocess`, `os.system` - System calls
- `eval()`, `exec()` - Dynamic code execution

## Testing

Run the test script:
```bash
python test_upload.py
```

This will test:
1. Single file upload
2. ZIP package upload
3. Multiple files upload
4. Invalid upload rejection (security check)

## Python Example

```python
import requests

# Upload a ZIP package
with open('strategy_package.zip', 'rb') as f:
    files = {'strategy_zip': f}
    data = {'key': 'YOUR_API_KEY'}
    
    response = requests.post(
        'http://localhost:8000/api/v1/team/test1/upload-strategy-package',
        files=files,
        data=data
    )
    
    result = response.json()
    print(result)
```

## Response Format

**Success Response:**
```json
{
    "success": true,
    "message": "Strategy uploaded successfully",
    "team_id": "test1",
    "files_uploaded": ["strategy.py", "indicators.py", "utils.py"],
    "file_count": 3,
    "path": "/opt/qtc/external_strategies/test1",
    "validation": {
        "all_files_validated": true,
        "security_checks_passed": true
    },
    "note": "Strategy will be loaded on the next trading cycle"
}
```

**Error Response:**
```json
{
    "detail": "Validation failed: Disallowed import: requests"
}
```

## Multi-File Strategy Structure

When using multiple files, you can organize your strategy like this:

**strategy.py** (entry point):
```python
from indicators import calculate_rsi
from risk_manager import RiskManager
import config

class Strategy:
    def __init__(self, **kwargs):
        self.risk_manager = RiskManager()
    
    def generate_signal(self, team, bars, current_prices):
        # Use helper modules
        rsi = calculate_rsi(bars['AAPL']['close'])
        # ...
```

**indicators.py** (helper):
```python
import numpy as np

def calculate_rsi(prices, period=14):
    # RSI calculation
    pass
```

**risk_manager.py** (helper):
```python
class RiskManager:
    def calculate_position_size(self, cash, price):
        # Position sizing logic
        pass
```

**config.py** (constants):
```python
MAX_POSITION = 0.10
RSI_OVERSOLD = 30
```

## How It Works

1. **Upload**: Files are uploaded via API with team authentication
2. **Validation**: All Python files are checked for security violations
3. **Storage**: Files are saved to `/opt/qtc/external_strategies/{team_id}/`
4. **Registry Update**: Team registry is updated to use uploaded files
5. **Loading**: Strategy is loaded on the next trading cycle

## Notes

- Strategy uploads replace any existing strategy for the team
- All files must pass security validation
- The orchestrator will automatically load the new strategy on the next trading cycle
- Maximum file size: 10 MB per file (ZIP upload)
- Supported formats: `.py` (single/multiple), `.zip` (package)

## Get Your API Key

Your API key is stored in `/opt/qtc/data/api_keys.json`:
```bash
cat /opt/qtc/data/api_keys.json
```

Example:
```json
{
  "test1": "XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg",
  "test2": "RagxKEKZwVo2ow9kwbJY062gWtfr7BepffWT7eMlg6A"
}
```

