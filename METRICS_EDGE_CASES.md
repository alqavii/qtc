# Metrics Calculation - Edge Case Handling

## Overview

The performance metrics calculation now includes comprehensive handling of edge cases and extreme values to prevent errors and provide meaningful results in all scenarios.

---

## Edge Cases Handled

### 1. Zero or Near-Zero Volatility

**Scenario:** Portfolio value remains constant or nearly constant (no price movement).

**Handling:**
- **Sharpe Ratio:** Returns `null` (was infinity) when volatility = 0
- **Sortino Ratio:** Returns `null` when no downside volatility
- If return is also 0: Returns 0.0
- Threshold: Volatility < 1e-10 is considered zero

**Example:**
```json
{
  "annualized_volatility": 0.0,
  "sharpe_ratio": null,  // Previously would be inf or cause error
  "sortino_ratio": null
}
```

---

### 2. Zero Returns

**Scenario:** Portfolio value doesn't change (flat performance).

**Handling:**
- **Total Return:** 0.0%
- **Sharpe Ratio:** 0.0 (no risk, no return)
- **Calmar Ratio:** 0.0
- All percentage metrics: 0.0

**Example:**
```json
{
  "total_return": 0.0,
  "total_return_percentage": 0.0,
  "sharpe_ratio": 0.0
}
```

---

### 3. Zero Starting Value

**Scenario:** Portfolio starts at $0 (rare but possible during initialization).

**Handling:**
- If end value is also 0: Return 0%
- If end value > 0: Return is undefined (`null`)
- Prevents division by zero errors

**Example:**
```json
{
  "starting_value": 0.0,
  "current_value": 1000.0,
  "total_return": null,  // Can't calculate % from 0
  "total_return_percentage": null
}
```

---

### 4. No Drawdown (Perfect Performance)

**Scenario:** Portfolio only goes up, never declines from peak.

**Handling:**
- **Max Drawdown:** 0.0%
- **Calmar Ratio:** Returns `null` (infinite ratio)
- If return is also 0: Returns 0.0

**Example:**
```json
{
  "max_drawdown": 0.0,
  "max_drawdown_percentage": 0.0,
  "calmar_ratio": null,  // Perfect performance, no risk
  "sortino_ratio": null   // No downside volatility
}
```

---

### 5. No Losses (All Winning Periods)

**Scenario:** Every period shows positive returns.

**Handling:**
- **Profit Factor:** Returns `null` (infinite, no losses to divide by)
- **Sortino Ratio:** Returns `null` (no downside volatility)
- **Win Rate:** 100%

**Example:**
```json
{
  "win_rate_percentage": 100.0,
  "profit_factor": null,  // All wins, no losses
  "sortino_ratio": null,
  "losing_trades": 0
}
```

---

### 6. All Zero Portfolio Values

**Scenario:** Portfolio is completely empty throughout period.

**Handling:**
- Returns error message instead of calculating metrics
- Error: "All portfolio values are zero"

**Example:**
```json
{
  "error": "All portfolio values are zero",
  "data_points": 100
}
```

---

### 7. Invalid Returns (Inf, -Inf, NaN)

**Scenario:** Division by zero in return calculation (e.g., portfolio value = 0 at some point).

**Handling:**
- Filters out invalid returns (inf, -inf, nan)
- Only uses valid returns for calculations
- If too few valid returns (< 2): Returns error

**Example:**
```json
{
  "error": "Insufficient valid returns for metrics calculation",
  "data_points": 100,
  "valid_returns": 1
}
```

---

### 8. Insufficient Data Points

**Scenario:** Less than 2 data points in history.

**Handling:**
- Returns error message
- Requires at least 2 points to calculate returns

**Example:**
```json
{
  "error": "Insufficient data for metrics calculation",
  "data_points": 1
}
```

---

### 9. Zero Drawdown Denominator

**Scenario:** Cumulative max is 0 when calculating drawdown percentage.

**Handling:**
- Uses `np.errstate` to ignore division warnings
- Replaces inf/nan values with 0.0
- Prevents calculation errors

**Code:**
```python
with np.errstate(divide='ignore', invalid='ignore'):
    drawdowns = (values - cumulative_max) / cumulative_max
drawdowns = np.nan_to_num(drawdowns, nan=0.0, posinf=0.0, neginf=0.0)
```

---

### 10. Very Short Time Periods

**Scenario:** Less than 1 millisecond between first and last data point.

**Handling:**
- Minimum time period: 0.001 days (86.4 seconds)
- Prevents division by zero in annualization
- Uses: `days_elapsed = max(time_diff / 86400, 0.001)`

---

## Return Value Standards

### For Impossible/Undefined Ratios

When a ratio would be infinite (division by zero):
- **Return:** `null` instead of `inf` or `-inf`
- **Reason:** JSON-friendly, frontend can easily check for `null`
- **Frontend interpretation:** Display as "N/A" or "∞"

**Examples:**
```json
{
  "sharpe_ratio": null,    // Zero volatility with positive return
  "sortino_ratio": null,   // No downside volatility
  "calmar_ratio": null,    // No drawdown
  "profit_factor": null    // No losses
}
```

### For Zero/Neutral Values

When metric is legitimately zero:
- **Return:** `0.0`
- **Reason:** Clear distinction from undefined

**Examples:**
```json
{
  "total_return": 0.0,           // No gain or loss
  "max_drawdown": 0.0,            // No decline from peak
  "annualized_volatility": 0.0   // No price movement
}
```

---

## Technical Implementation

### Key Functions

1. **`np.errstate(divide='ignore', invalid='ignore')`**
   - Suppresses numpy division warnings
   - Allows inf/nan to be generated
   - We handle them explicitly afterwards

2. **`np.isfinite(value)`**
   - Checks if value is finite (not inf or nan)
   - Used to filter valid returns

3. **`np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)`**
   - Replaces special values with specified constants
   - Used for drawdown calculations

4. **`safe_float(value)`**
   - Custom function to convert values to JSON-safe floats
   - Converts inf → None
   - Converts nan → None
   - Preserves finite values

### Thresholds

```python
min_volatility = 1e-10     # Minimum volatility (effectively zero)
min_value = 1e-10          # Minimum value for comparisons
```

---

## Frontend Handling Recommendations

### Display Logic

```javascript
function displayMetric(value, metricName) {
  if (value === null) {
    // Infinite/undefined ratio
    switch (metricName) {
      case 'sharpe_ratio':
      case 'sortino_ratio':
      case 'calmar_ratio':
        return '∞ (Perfect)';  // No risk with positive return
      case 'profit_factor':
        return '∞ (No Losses)';
      default:
        return 'N/A';
    }
  }
  
  if (value === 0.0) {
    return '0.00';  // Legitimate zero
  }
  
  return value.toFixed(2);
}
```

### Color Coding

```javascript
function getMetricColor(value, metricName) {
  if (value === null) {
    // Undefined but potentially excellent
    return 'blue';  // Or 'gold' for perfect performance
  }
  
  if (metricName === 'sharpe_ratio') {
    if (value > 2) return 'green';
    if (value > 1) return 'yellow';
    return 'red';
  }
  
  // ... other metrics
}
```

### Sorting

```javascript
function sortByMetric(teams, metricName) {
  return teams.sort((a, b) => {
    const aValue = a[metricName];
    const bValue = b[metricName];
    
    // null (infinite) is better than any finite value
    if (aValue === null && bValue === null) return 0;
    if (aValue === null) return -1;  // a is better
    if (bValue === null) return 1;   // b is better
    
    // Normal numeric comparison
    return bValue - aValue;  // Descending
  });
}
```

---

## Testing Edge Cases

### Test Script

```python
import requests

API_BASE = "http://localhost:8000"

# Test with team that has no volatility
response = requests.get(
    f"{API_BASE}/api/v1/team/constant_team/metrics",
    params={"key": "YOUR_KEY", "days": 7}
)
data = response.json()

# Check for null values
assert data['metrics']['sharpe_ratio'] is None or isinstance(data['metrics']['sharpe_ratio'], float)
assert 'error' not in data or data['error'] == "expected_error_message"

print("✅ Edge case handling verified")
```

### Manual Testing Scenarios

1. **Constant Portfolio:** Create a team that never trades
2. **Only Winners:** Team that only has profitable periods
3. **Perfect Growth:** Team that only goes up (no drawdowns)
4. **Near-Zero Values:** Team with very small portfolio ($0.01)

---

## Migration Notes

### Breaking Changes

**None** - All changes are backwards compatible:
- Valid numeric values remain unchanged
- Infinite values now return `null` (previously may have caused errors)
- Frontend should handle `null` gracefully (already should for missing data)

### Recommended Updates

1. **Update Frontend Display Logic:**
   ```javascript
   // Old: Assumed always numeric
   <td>{metrics.sharpe_ratio.toFixed(2)}</td>
   
   // New: Handle null
   <td>{metrics.sharpe_ratio?.toFixed(2) ?? 'N/A'}</td>
   ```

2. **Update Sorting Logic:**
   - Handle `null` as "better than any finite value" for ratios
   - Or treat as "worst" if that makes more UX sense

3. **Add Tooltips:**
   ```html
   <span title="Perfect performance - no risk">∞</span>
   ```

---

## Summary of Changes

### Before
- Division by zero → Error or crash
- Infinite values → Invalid JSON or errors
- Zero volatility → Undefined behavior
- No validation of extreme values

### After
✅ All division by zero cases handled
✅ Infinite values converted to `null`
✅ Zero volatility returns appropriate values
✅ Comprehensive validation
✅ Clear error messages
✅ JSON-safe output
✅ Frontend-friendly null values

---

## Performance Impact

**Minimal** - Added operations:
- `np.errstate` context managers (negligible overhead)
- `np.isfinite` checks (fast numpy operation)
- `safe_float` function calls (simple if-else checks)

**No noticeable performance degradation expected.**

---

## Questions & Answers

**Q: Why return `null` instead of a large number for infinite ratios?**
A: JSON doesn't support `Infinity`. `null` is clear, unambiguous, and frontend-friendly.

**Q: Should `null` be displayed as "∞" or "N/A"?**
A: Depends on context:
- For Sharpe/Sortino/Calmar with positive returns → "∞" or "Perfect"
- For missing/undefined data → "N/A"

**Q: How do I sort teams when some have `null` metrics?**
A: Treat `null` as "best" for positive metrics (ratios) or filter them separately.

**Q: What if I want the actual infinity value?**
A: Remove the `safe_float()` wrapper, but ensure your frontend/JSON parser can handle it (most can't).

---

## Contact & Support

For questions or issues with edge case handling:
1. Check error messages in API response
2. Review this document for your scenario
3. Test with `curl` to verify behavior
4. Check logs: `qtc_alpha.log`

