# Quick Start: Upload Your Strategy

**⚡ Get your trading strategy running in 5 minutes**

---

## Step 1: Get Your API Key

```bash
# Check your API key
cat /opt/qtc/data/api_keys.json
```

Example output:
```json
{
  "team-alpha": "XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg"
}
```

Copy your API key! ✅

---

## Step 2: Create Your Strategy

### Simple Strategy (single file)

**strategy.py:**
```python
import numpy as np

class Strategy:
    def __init__(self, **kwargs):
        self.symbol = kwargs.get('symbol', 'AAPL')
    
    def generate_signal(self, team, bars, current_prices):
        if self.symbol not in bars:
            return None
        
        closes = bars[self.symbol].get('close', [])
        if len(closes) < 2:
            return None
        
        # Simple momentum
        if closes[-1] > closes[-2]:
            return {
                "symbol": self.symbol,
                "action": "buy",
                "quantity": 10,
                "price": current_prices[self.symbol]
            }
        
        return None
```

### Complex Strategy (multiple files)

Create a folder with:
- `strategy.py` (main entry point)
- `indicators.py` (helpers)
- `utils.py` (utilities)

Then ZIP it:
```bash
zip strategy_package.zip strategy.py indicators.py utils.py
```

---

## Step 3: Upload Your Strategy

### Option A: Using cURL (Terminal)

**Single file:**
```bash
curl -X POST "http://localhost:8000/api/v1/team/YOUR_TEAM/upload-strategy" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_file=@strategy.py"
```

**ZIP package:**
```bash
curl -X POST "http://localhost:8000/api/v1/team/YOUR_TEAM/upload-strategy-package" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_zip=@strategy_package.zip"
```

### Option B: Using Python

```python
import requests

# Replace these
TEAM_ID = "your-team-id"
API_KEY = "your-api-key"

# Single file upload
with open('strategy.py', 'rb') as f:
    response = requests.post(
        f'http://localhost:8000/api/v1/team/{TEAM_ID}/upload-strategy',
        files={'strategy_file': f},
        data={'key': API_KEY}
    )

print(response.json())
```

### Option C: Using Web Form (Frontend)

```javascript
const formData = new FormData();
formData.append('key', apiKey);
formData.append('strategy_file', file);

const response = await fetch(
    `http://localhost:8000/api/v1/team/${teamId}/upload-strategy`,
    { method: 'POST', body: formData }
);

const result = await response.json();
console.log(result);
```

---

## Step 4: Verify Upload

### Check Response

**Success:**
```json
{
    "success": true,
    "message": "Strategy uploaded successfully for team-alpha",
    "files_uploaded": ["strategy.py"],
    "path": "/opt/qtc/external_strategies/team-alpha"
}
```

**Error:**
```json
{
    "detail": "Validation failed: Disallowed import: requests"
}
```

### Check Files

```bash
# See your uploaded files
ls -la /opt/qtc/external_strategies/YOUR_TEAM/
```

### Check Logs

```bash
# Watch orchestrator logs
tail -f /opt/qtc/qtc_alpha.log | grep YOUR_TEAM
```

---

## Step 5: Monitor Your Strategy

### Check Performance

```bash
# Get team metrics
curl "http://localhost:8000/api/v1/team/YOUR_TEAM/metrics?key=YOUR_KEY"
```

### View Trades

```bash
# Get trade history
curl "http://localhost:8000/api/v1/team/YOUR_TEAM/trades?key=YOUR_KEY"
```

### Check Leaderboard

```bash
# Public leaderboard
curl "http://localhost:8000/leaderboard"
```

---

## Common Issues

### ❌ "Invalid API key"
**Solution:** Check your key in `data/api_keys.json`

### ❌ "Disallowed import: requests"
**Solution:** Remove network imports. Use only: numpy, pandas, scipy

### ❌ "strategy.py not found"
**Solution:** Ensure your ZIP or upload includes `strategy.py`

### ❌ "Invalid file path in ZIP"
**Solution:** Don't use `..` in paths, keep files at root of ZIP

---

## Available Imports

### ✅ Allowed
- `numpy`, `pandas`, `scipy` - Data processing
- `math`, `statistics`, `decimal` - Math
- `collections`, `typing` - Standard library

### ❌ Blocked
- `requests`, `urllib` - Network
- `open()`, file I/O - File access
- `subprocess` - System calls
- `eval()`, `exec()` - Dynamic code

---

## Full Documentation

- **Upload API:** [STRATEGY_UPLOAD_API.md](STRATEGY_UPLOAD_API.md)
- **Implementation:** [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Strategy Guide:** [strategy_starter/README.md](strategy_starter/README.md)
- **System Docs:** [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)

---

## Test Examples

Run the included tests:

```bash
# Python test
cd /opt/qtc/test_strategy_upload
python3 test_upload.py

# Bash test
./test_curl.sh
```

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Upload single file | `curl -X POST ".../upload-strategy" -F "key=..." -F "strategy_file=@strategy.py"` |
| Upload ZIP | `curl -X POST ".../upload-strategy-package" -F "key=..." -F "strategy_zip=@pkg.zip"` |
| Get API key | `cat data/api_keys.json` |
| Check files | `ls external_strategies/YOUR_TEAM/` |
| View logs | `tail -f qtc_alpha.log` |
| Get metrics | `curl ".../team/YOUR_TEAM/metrics?key=..."` |

---

## Need Help?

1. **Read:** [STRATEGY_UPLOAD_API.md](STRATEGY_UPLOAD_API.md)
2. **Test:** Run `python3 test_strategy_upload/test_upload.py`
3. **Check:** Logs in `qtc_alpha.log` and `qtc_alpha_errors.log`
4. **Verify:** Files in `external_strategies/{your_team}/`

---

**Ready to trade? Upload your strategy now! 🚀**

*Updated: October 13, 2025*

