# Strategy Upload API Documentation

**Version:** 1.0  
**Last Updated:** October 13, 2025

---

## Overview

The QTC Alpha platform now supports **direct file uploads** for trading strategies via REST API. Teams can upload their Python strategy files through a web interface or programmatically, **without needing to use GitHub**.

### Why Upload via API?

✅ **Simpler** - No Git knowledge required  
✅ **Faster** - Instant upload and deployment  
✅ **Flexible** - Single file or multi-file strategies  
✅ **Secure** - Built-in validation and sandboxing  

---

## Authentication

All upload endpoints require **team API key authentication**.

### Finding Your API Key

Your API key is stored in `/opt/qtc/data/api_keys.json`:

```bash
cat data/api_keys.json
```

Example:
```json
{
  "team-alpha": "XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg",
  "team-beta": "RagxKEKZwVo2ow9kwbJY062gWtfr7BepffWT7eMlg6A"
}
```

---

## Upload Endpoints

### 1. Single File Upload

**Endpoint:** `POST /api/v1/team/{team_id}/upload-strategy`

Upload a single `strategy.py` file. Best for simple strategies.

**Parameters:**
- `team_id` (path): Your team identifier
- `key` (form): Your team API key
- `strategy_file` (file): Python file to upload

**Example (curl):**
```bash
curl -X POST "http://localhost:8000/api/v1/team/team-alpha/upload-strategy" \
  -F "key=XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg" \
  -F "strategy_file=@strategy.py"
```

**Example (Python):**
```python
import requests

with open('strategy.py', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/team/team-alpha/upload-strategy',
        files={'strategy_file': f},
        data={'key': 'YOUR_API_KEY'}
    )
    
print(response.json())
```

**Example (JavaScript/Fetch):**
```javascript
const formData = new FormData();
formData.append('key', 'YOUR_API_KEY');
formData.append('strategy_file', fileInput.files[0]);

const response = await fetch(
    'http://localhost:8000/api/v1/team/team-alpha/upload-strategy',
    {
        method: 'POST',
        body: formData
    }
);

const result = await response.json();
console.log(result);
```

**Success Response:**
```json
{
    "success": true,
    "message": "Strategy uploaded successfully for team-alpha",
    "team_id": "team-alpha",
    "files_uploaded": ["strategy.py"],
    "path": "/opt/qtc/external_strategies/team-alpha",
    "note": "Strategy will be loaded on the next trading cycle"
}
```

---

### 2. ZIP Package Upload (Recommended for Multi-File)

**Endpoint:** `POST /api/v1/team/{team_id}/upload-strategy-package`

Upload a ZIP file containing `strategy.py` and helper modules.

**Parameters:**
- `team_id` (path): Your team identifier
- `key` (form): Your team API key
- `strategy_zip` (file): ZIP file containing Python files

**ZIP Structure:**
```
strategy_package.zip
├── strategy.py          # Required entry point
├── indicators.py        # Helper module (optional)
├── risk_manager.py      # Helper module (optional)
└── utils.py             # Helper module (optional)
```

**Example (curl):**
```bash
# First, create the ZIP
zip strategy_package.zip strategy.py indicators.py utils.py

# Upload
curl -X POST "http://localhost:8000/api/v1/team/team-alpha/upload-strategy-package" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_zip=@strategy_package.zip"
```

**Example (Python):**
```python
import requests

with open('strategy_package.zip', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/team/team-alpha/upload-strategy-package',
        files={'strategy_zip': f},
        data={'key': 'YOUR_API_KEY'}
    )

result = response.json()
print(f"Uploaded {result['file_count']} files: {result['files_uploaded']}")
```

**Example (JavaScript):**
```javascript
const formData = new FormData();
formData.append('key', apiKey);
formData.append('strategy_zip', zipFile);

const response = await fetch(
    `${API_BASE}/api/v1/team/${teamId}/upload-strategy-package`,
    {
        method: 'POST',
        body: formData
    }
);

const result = await response.json();
```

**Success Response:**
```json
{
    "success": true,
    "message": "Strategy package uploaded successfully for team-alpha",
    "team_id": "team-alpha",
    "files_uploaded": [
        "strategy.py",
        "indicators.py",
        "risk_manager.py",
        "utils.py"
    ],
    "file_count": 4,
    "path": "/opt/qtc/external_strategies/team-alpha",
    "validation": {
        "all_files_validated": true,
        "security_checks_passed": true
    },
    "note": "Strategy will be loaded on the next trading cycle"
}
```

---

### 3. Multiple Files Upload

**Endpoint:** `POST /api/v1/team/{team_id}/upload-multiple-files`

Upload multiple Python files individually (alternative to ZIP).

**Parameters:**
- `team_id` (path): Your team identifier
- `key` (form): Your team API key
- `files` (files): Multiple Python files (must include strategy.py)

**Example (curl):**
```bash
curl -X POST "http://localhost:8000/api/v1/team/team-alpha/upload-multiple-files" \
  -F "key=YOUR_API_KEY" \
  -F "files=@strategy.py" \
  -F "files=@indicators.py" \
  -F "files=@utils.py"
```

**Example (Python):**
```python
import requests

files_to_upload = [
    ('files', open('strategy.py', 'rb')),
    ('files', open('indicators.py', 'rb')),
    ('files', open('utils.py', 'rb'))
]

response = requests.post(
    'http://localhost:8000/api/v1/team/team-alpha/upload-multiple-files',
    files=files_to_upload,
    data={'key': 'YOUR_API_KEY'}
)

# Don't forget to close files
for _, fh in files_to_upload:
    fh.close()
```

**Example (JavaScript):**
```javascript
const formData = new FormData();
formData.append('key', apiKey);

// Add multiple files
for (const file of fileInput.files) {
    formData.append('files', file);
}

const response = await fetch(
    `${API_BASE}/api/v1/team/${teamId}/upload-multiple-files`,
    {
        method: 'POST',
        body: formData
    }
);
```

---

## Multi-File Strategy Structure

### Example: RSI Strategy with Helpers

**strategy.py** (Main entry point):
```python
from indicators import calculate_rsi
from risk_manager import RiskManager
import config

class Strategy:
    def __init__(self, **kwargs):
        self.risk_manager = RiskManager(max_position=config.MAX_POSITION)
        self.rsi_period = kwargs.get('rsi_period', 14)
    
    def generate_signal(self, team, bars, current_prices):
        symbol = "AAPL"
        
        if symbol not in bars:
            return None
        
        closes = bars[symbol].get('close', [])
        rsi = calculate_rsi(closes, self.rsi_period)
        
        if rsi < config.RSI_OVERSOLD:
            quantity = self.risk_manager.calculate_position_size(
                team['cash'], 
                current_prices[symbol]
            )
            return {
                "symbol": symbol,
                "action": "buy",
                "quantity": quantity,
                "price": current_prices[symbol],
                "reason": f"RSI oversold: {rsi:.1f}"
            }
        
        return None
```

**indicators.py** (Helper module):
```python
import numpy as np

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    if len(prices) < period + 1:
        return 50.0
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

**risk_manager.py** (Helper module):
```python
class RiskManager:
    def __init__(self, max_position=0.10):
        self.max_position = max_position
    
    def calculate_position_size(self, cash, price):
        max_dollar = cash * self.max_position
        return max(1, int(max_dollar / price))
```

**config.py** (Constants):
```python
MAX_POSITION = 0.10  # 10% per position
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
```

---

## Security Validation

All uploaded files are automatically validated for security.

### ✅ Allowed Imports

- **Scientific:** `numpy`, `pandas`, `scipy`
- **Math:** `math`, `statistics`, `decimal`
- **Standard:** `collections`, `typing`

### ❌ Blocked Operations

- **Network:** `requests`, `urllib`, `socket`, `http`
- **File I/O:** `open()`, file operations
- **System:** `subprocess`, `os.system`, `eval()`, `exec()`
- **Dynamic:** `__import__()`, `importlib` (for user code)

### Validation Process

1. **Syntax Check** - Valid Python code
2. **Import Validation** - Only allowed imports
3. **AST Scanning** - No dangerous operations
4. **Interface Check** - Must have `Strategy` class with `generate_signal` method

**Example Rejection:**
```python
# This will be REJECTED
import requests  # Network access not allowed

class Strategy:
    def generate_signal(self, team, bars, current_prices):
        # Attempt to make HTTP request
        data = requests.get('http://api.example.com')  # BLOCKED
        return None
```

**Error Response:**
```json
{
    "detail": "Validation failed: Disallowed import: requests in strategy.py"
}
```

---

## Error Handling

### Authentication Errors

**401 Unauthorized**
```json
{
    "detail": "Invalid API key"
}
```

**Solution:** Check your API key in `data/api_keys.json`

### Validation Errors

**400 Bad Request - Missing strategy.py**
```json
{
    "detail": "Strategy validation failed: strategy.py not found in upload. This file is required as the entry point."
}
```

**400 Bad Request - Invalid Import**
```json
{
    "detail": "Validation failed: Disallowed import: requests in strategy.py"
}
```

**400 Bad Request - Invalid File Type**
```json
{
    "detail": "File must be a Python (.py) file"
}
```

**400 Bad Request - Invalid ZIP**
```json
{
    "detail": "Invalid file path in ZIP: ../../../etc/passwd. Paths must be relative and not use .."
}
```

---

## File Size Limits

- **Single file:** No hard limit (but must be reasonable)
- **ZIP file:** 10 MB per file in archive
- **Multiple files:** No hard limit per file

---

## Deployment Timeline

After successful upload:

1. **Immediate:** Files saved to `external_strategies/{team_id}/`
2. **Immediate:** Team registry updated
3. **Next trading cycle:** Strategy loaded and executed (typically within 1 minute)

To verify your strategy is loaded, check the orchestrator logs:
```bash
tail -f qtc_alpha.log | grep "your-team-id"
```

---

## Complete Frontend Example

### HTML Form
```html
<form id="upload-form">
    <label>Team ID:</label>
    <input type="text" id="team-id" value="team-alpha" />
    
    <label>API Key:</label>
    <input type="password" id="api-key" />
    
    <label>Strategy Files:</label>
    <input type="file" id="files" multiple accept=".py,.zip" />
    
    <button type="submit">Upload Strategy</button>
</form>
<div id="result"></div>
```

### JavaScript
```javascript
document.getElementById('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const teamId = document.getElementById('team-id').value;
    const apiKey = document.getElementById('api-key').value;
    const files = document.getElementById('files').files;
    
    const formData = new FormData();
    formData.append('key', apiKey);
    
    // Determine upload type
    let endpoint;
    if (files[0].name.endsWith('.zip')) {
        // ZIP upload
        endpoint = `/api/v1/team/${teamId}/upload-strategy-package`;
        formData.append('strategy_zip', files[0]);
    } else if (files.length === 1) {
        // Single file
        endpoint = `/api/v1/team/${teamId}/upload-strategy`;
        formData.append('strategy_file', files[0]);
    } else {
        // Multiple files
        endpoint = `/api/v1/team/${teamId}/upload-multiple-files`;
        for (let file of files) {
            formData.append('files', file);
        }
    }
    
    try {
        const response = await fetch(`http://localhost:8000${endpoint}`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            document.getElementById('result').innerHTML = `
                <div class="success">
                    ✓ ${result.message}<br>
                    Files: ${result.files_uploaded.join(', ')}<br>
                    Path: ${result.path}
                </div>
            `;
        } else {
            document.getElementById('result').innerHTML = `
                <div class="error">
                    ✗ Upload failed: ${result.detail}
                </div>
            `;
        }
    } catch (error) {
        document.getElementById('result').innerHTML = `
            <div class="error">
                ✗ Error: ${error.message}
            </div>
        `;
    }
});
```

---

## Testing

Test files and scripts are provided in `test_strategy_upload/`:

```bash
# Using Python
cd test_strategy_upload
python test_upload.py

# Using bash/curl
./test_curl.sh
```

---

## FAQ

### Q: Can I upload strategies from the command line?

**A:** Yes! Use curl:
```bash
curl -X POST "http://localhost:8000/api/v1/team/YOUR_TEAM/upload-strategy" \
  -F "key=YOUR_KEY" \
  -F "strategy_file=@strategy.py"
```

### Q: How do I create a ZIP file with my strategy?

**A:** 
```bash
# Linux/Mac
zip strategy_package.zip strategy.py indicators.py utils.py

# Windows (PowerShell)
Compress-Archive -Path strategy.py,indicators.py,utils.py -DestinationPath strategy_package.zip
```

### Q: Can helper modules import each other?

**A:** Yes! As long as all files are in the same upload and all pass security validation.

```python
# indicators.py
from utils import normalize_array  # ✓ Works if utils.py is uploaded

# strategy.py
from indicators import calculate_rsi  # ✓ Works
```

### Q: What happens to my old strategy when I upload a new one?

**A:** The old strategy is **completely replaced**. All files in the strategy directory are removed and replaced with the new upload.

### Q: How long until my new strategy is active?

**A:** Your strategy will be loaded on the **next trading cycle** (typically within 1 minute during market hours).

### Q: Can I see if my upload worked?

**A:** Yes, check:
1. The API response (success/error)
2. Files in `/opt/qtc/external_strategies/{your_team}/`
3. Orchestrator logs: `tail -f qtc_alpha.log`

---

## Support

For issues or questions:
1. Check the error message in the API response
2. Verify your API key
3. Ensure all imports are allowed
4. Check the orchestrator logs
5. Review test examples in `test_strategy_upload/`

---

**Last Updated:** October 13, 2025  
**API Version:** 1.0

