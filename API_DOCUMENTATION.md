# QTC Alpha API Documentation

**Version:** 1.0  
**Base URL:** `http://your-server:8000` (or `https://your-domain.com` in production)  
**Last Updated:** October 10, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
   - [Public Endpoints](#public-endpoints)
   - [Team-Authenticated Endpoints](#team-authenticated-endpoints)
4. [Data Formats](#data-formats)
5. [Usage Examples](#usage-examples)
6. [Frontend Integration](#frontend-integration)
7. [Rate Limits & Best Practices](#rate-limits--best-practices)
8. [Error Handling](#error-handling)

---

## Overview

The QTC Alpha API provides both public and authenticated endpoints for accessing trading competition data. The API supports:

- **Real-time leaderboard data** (updated every minute)
- **Historical portfolio performance** for visualizations
- **Team-specific metrics and trade history**
- **Server-Sent Events (SSE)** for live activity streams

**API Features:**
- RESTful JSON API
- CORS enabled for browser access
- Server-Sent Events for real-time updates
- Rate-limited to prevent abuse

---

## Authentication

### Public Endpoints
No authentication required. These endpoints are accessible to anyone.

### Team-Authenticated Endpoints
Require a **Team API Key** passed as a query parameter.

**How to get your API key:**
1. Check `data/api_keys.json` on the server
2. Your key is automatically generated when your team is added
3. Format: `{"team_id": "your_api_key"}`

**Example:**
```json
{
  "test1": "XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg",
  "test2": "RagxKEKZwVo2ow9kwbJY062gWtfr7BepffWT7eMlg6A"
}
```

**Authentication Method:**
Pass your key as a query parameter named `key`:
```
GET /api/v1/team/test1/history?key=XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg
```

---

## Endpoints

### Public Endpoints

#### 1. Get Current Leaderboard
**GET** `/leaderboard`

Returns current rankings of all teams sorted by portfolio value.

**Parameters:** None

**Response:**
```json
{
  "leaderboard": [
    {
      "team_id": "test1",
      "portfolio_value": 10542.75
    },
    {
      "team_id": "test2",
      "portfolio_value": 9875.50
    }
  ]
}
```

**Use Cases:**
- Display current rankings on a leaderboard page
- Show who's currently winning
- Update every 60 seconds for real-time feel

---

#### 2. Get Historical Data for All Teams
**GET** `/api/v1/leaderboard/history`

Returns time-series portfolio data for all teams (public endpoint).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Days to look back (1-365) |
| `limit` | integer | 500 | Max data points per team (1-5000) |

**Example Request:**
```
GET /api/v1/leaderboard/history?days=7&limit=500
```

**Response:**
```json
{
  "days": 7,
  "teams": {
    "test1": [
      {
        "timestamp": "2025-10-10T14:30:00+00:00",
        "value": 10500.25
      },
      {
        "timestamp": "2025-10-10T14:31:00+00:00",
        "value": 10502.50
      }
    ],
    "test2": [
      {
        "timestamp": "2025-10-10T14:30:00+00:00",
        "value": 9800.00
      }
    ]
  }
}
```

**Use Cases:**
- Multi-line charts comparing all teams
- Racing bar chart animations
- Historical leaderboard snapshots

---

#### 3. Get Recent Activity Stream
**GET** `/activity/recent`

Returns recent activity log entries.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 100 | Max entries to return (1-500) |

**Response:**
```json
{
  "activity": [
    {
      "timestamp": "2025-10-10T14:30:00+00:00",
      "message": "received minutebars for 14:30 (5 symbols)"
    }
  ]
}
```

---

#### 4. Stream Live Activity (SSE)
**GET** `/activity/stream`

Server-Sent Events endpoint for real-time activity updates.

**Parameters:** None

**Response Format:** `text/event-stream`

**Example (JavaScript):**
```javascript
const eventSource = new EventSource('http://localhost:8000/activity/stream');

eventSource.onmessage = (event) => {
  console.log('Activity:', event.data);
};

eventSource.onerror = () => {
  console.log('Connection closed');
  eventSource.close();
};
```

---

### Team-Authenticated Endpoints

#### 5. Get Team Status
**GET** `/line/{team_key}`

Returns current snapshot and metrics for a team using their API key.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `team_key` | string (path) | Team API key |

**Example Request:**
```
GET /line/XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg
```

**Response:**
```json
{
  "team_id": "test1",
  "snapshot": {
    "timestamp": "2025-10-10T14:30:00+00:00",
    "cash": 5000.00,
    "market_value": 10500.25,
    "positions": {
      "NVDA": {
        "quantity": 10,
        "avg_cost": 500.0,
        "value": 5500.25
      }
    }
  },
  "metrics": {
    "total_trades": 25,
    "win_rate": 0.60
  }
}
```

---

#### 6. Get Team Status (CLI Format)
**GET** `/{team_key}`

Returns plain-text one-liner for command-line display.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `team_key` | string (path) | Team API key |

**Response:** `text/plain`
```
test1 | Cash: $5,000.00 | Portfolio Value: $10,500.25 | Positions: [["NVDA", $500.00, 10]]
```

**Use in Terminal:**
```bash
curl http://localhost:8000/XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg
```

---

#### 7. Get Team Historical Data
**GET** `/api/v1/team/{team_id}/history`

Returns time-series portfolio data for a specific team.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |
| `days` | integer | 7 | Days to look back (1-365) |
| `limit` | integer | 1000 | Max data points (1-10000) |

**Example Request:**
```
GET /api/v1/team/test1/history?key=XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg&days=7&limit=1000
```

**Response:**
```json
{
  "team_id": "test1",
  "days": 7,
  "data_points": 1000,
  "history": [
    {
      "timestamp": "2025-10-03T09:30:00+00:00",
      "value": 10000.00
    },
    {
      "timestamp": "2025-10-03T09:31:00+00:00",
      "value": 10005.25
    },
    {
      "timestamp": "2025-10-10T14:30:00+00:00",
      "value": 10542.75
    }
  ]
}
```

**Use Cases:**
- Team-specific performance charts
- Calculate returns and drawdowns
- Track portfolio growth over time

---

#### 8. Get Team Trade History
**GET** `/api/v1/team/{team_id}/trades`

Returns recent executed trades for a team.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |
| `limit` | integer | 100 | Max trades to return (1-1000) |

**Example Request:**
```
GET /api/v1/team/test1/trades?key=XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg&limit=50
```

**Response:**
```json
{
  "team_id": "test1",
  "count": 25,
  "trades": [
    {
      "timestamp": "2025-10-10T14:30:00+00:00",
      "symbol": "NVDA",
      "side": "buy",
      "quantity": 10,
      "price": 500.25,
      "order_type": "market",
      "team_id": "test1"
    },
    {
      "timestamp": "2025-10-10T14:25:00+00:00",
      "symbol": "AAPL",
      "side": "sell",
      "quantity": 5,
      "price": 175.50
    }
  ]
}
```

**Use Cases:**
- Display trade history table
- Analyze trading patterns
- Track order execution

---

#### 9. Get Team Performance Metrics
**GET** `/api/v1/team/{team_id}/metrics`

Returns comprehensive performance metrics including Sharpe ratio, Sortino ratio, Calmar ratio, maximum drawdown, total return, and more.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |
| `days` | integer | all | Days to calculate over (1-365, null=all) |

**Example Request:**
```
GET /api/v1/team/test1/metrics?key=XBGuqdB54MVsyZ18BC6K3HwN3CaIiBC3vFdDsxMisUg&days=7
```

**Response:**
```json
{
  "team_id": "test1",
  "metrics": {
    "sharpe_ratio": 1.85,
    "sortino_ratio": 2.34,
    "calmar_ratio": 3.21,
    "max_drawdown": -0.0542,
    "max_drawdown_percentage": -5.42,
    "current_drawdown": -0.0023,
    "current_drawdown_percentage": -0.23,
    "total_return": 0.0542,
    "total_return_percentage": 5.42,
    "annualized_return": 0.1247,
    "annualized_return_percentage": 12.47,
    "annualized_volatility": 0.0673,
    "annualized_volatility_percentage": 6.73,
    "win_rate": 0.58,
    "win_rate_percentage": 58.0,
    "profit_factor": 1.45,
    "avg_win": 0.0012,
    "avg_loss": -0.0009,
    "total_trades": 250,
    "winning_trades": 145,
    "losing_trades": 105,
    "current_value": 10542.75,
    "starting_value": 10000.00,
    "peak_value": 10650.25,
    "trough_value": 9875.50,
    "max_drawdown_details": {
      "peak_value": 10650.25,
      "trough_value": 10075.30,
      "drawdown_amount": 574.95
    },
    "period": {
      "start": "2025-10-03T09:30:00+00:00",
      "end": "2025-10-10T16:00:00+00:00",
      "days": 7.27,
      "data_points": 2835
    }
  }
}
```

**Metrics Explained:**

| Metric | Description | Good Value |
|--------|-------------|------------|
| **Sharpe Ratio** | Risk-adjusted return | >1 good, >2 excellent |
| **Sortino Ratio** | Return vs downside volatility | >1 good, >2 excellent |
| **Calmar Ratio** | Return vs max drawdown | >1 good, >3 excellent |
| **Max Drawdown** | Largest peak-to-trough decline | Closer to 0 is better |
| **Total Return %** | Overall profit/loss since start | Positive is profitable |
| **Annualized Return %** | Expected yearly return | Higher is better |
| **Win Rate %** | Percentage of profitable periods | >50% is good |
| **Profit Factor** | Total wins / total losses | >1 is profitable, >2 is good |

**Use Cases:**
- Comprehensive performance analysis
- Risk assessment
- Strategy evaluation
- Detailed team dashboards

---

#### 10. Get Leaderboard with Metrics
**GET** `/api/v1/leaderboard/metrics`

Returns leaderboard with comprehensive performance metrics for all teams. Can be sorted by different criteria.

**Authentication:** None (public endpoint)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | all | Days to calculate over (1-365, null=all) |
| `sort_by` | string | portfolio_value | Sort by: portfolio_value, sharpe_ratio, total_return, calmar_ratio, sortino_ratio, annualized_return |

**Example Request:**
```
GET /api/v1/leaderboard/metrics?days=7&sort_by=sharpe_ratio
```

**Response:**
```json
{
  "leaderboard": [
    {
      "team_id": "test1",
      "rank": 1,
      "portfolio_value": 10542.75,
      "sharpe_ratio": 1.85,
      "sortino_ratio": 2.34,
      "calmar_ratio": 3.21,
      "max_drawdown": -0.0542,
      "max_drawdown_percentage": -5.42,
      "current_drawdown_percentage": -0.23,
      "total_return": 0.0542,
      "total_return_percentage": 5.42,
      "annualized_return": 0.1247,
      "annualized_return_percentage": 12.47,
      "annualized_volatility_percentage": 6.73,
      "win_rate_percentage": 58.0,
      "profit_factor": 1.45,
      "total_trades": 250,
      "current_value": 10542.75,
      "starting_value": 10000.00
    },
    {
      "team_id": "test2",
      "rank": 2,
      "portfolio_value": 9875.50,
      "sharpe_ratio": 1.62,
      "sortino_ratio": 2.01,
      "calmar_ratio": 2.85,
      "max_drawdown_percentage": -6.24,
      "total_return_percentage": 3.76,
      "annualized_return_percentage": 10.21
    }
  ],
  "sort_by": "sharpe_ratio",
  "calculation_period_days": 7
}
```

**Use Cases:**
- Enhanced leaderboard with risk-adjusted metrics
- Compare teams by different performance criteria
- Find best risk-adjusted performers
- Sort by Sharpe ratio instead of just portfolio value

---

## Data Formats

### Timestamp Format
All timestamps are in **ISO 8601 format with UTC timezone**:
```
2025-10-10T14:30:00+00:00
```

### Numeric Values
- **Portfolio values:** Float (e.g., `10500.25`)
- **Prices:** Float (e.g., `500.25`)
- **Quantities:** Integer or Float (e.g., `10` or `0.5` for fractional shares)

### Portfolio Snapshot Structure
```json
{
  "timestamp": "2025-10-10T14:30:00+00:00",
  "cash": 5000.00,
  "market_value": 10500.25,
  "positions": {
    "SYMBOL": {
      "quantity": 10,
      "avg_cost": 500.0,
      "value": 5000.0,
      "side": "long"
    }
  }
}
```

---

## Usage Examples

### Example 1: Fetch Current Leaderboard (JavaScript)

```javascript
async function fetchLeaderboard() {
  const response = await fetch('http://localhost:8000/leaderboard');
  const data = await response.json();
  
  console.log('Current Rankings:');
  data.leaderboard.forEach((team, index) => {
    console.log(`${index + 1}. ${team.team_id}: $${team.portfolio_value?.toLocaleString()}`);
  });
}

fetchLeaderboard();
```

**Output:**
```
Current Rankings:
1. test1: $10,542.75
2. test2: $9,875.50
```

---

### Example 2: Display Team Historical Chart (Chart.js)

```javascript
async function displayTeamChart(teamId, apiKey) {
  // Fetch historical data
  const response = await fetch(
    `http://localhost:8000/api/v1/team/${teamId}/history?key=${apiKey}&days=7&limit=500`
  );
  const data = await response.json();
  
  // Prepare data for Chart.js
  const chartData = {
    labels: data.history.map(h => new Date(h.timestamp)),
    datasets: [{
      label: `${teamId} Portfolio Value`,
      data: data.history.map(h => h.value),
      borderColor: 'rgb(75, 192, 192)',
      backgroundColor: 'rgba(75, 192, 192, 0.2)',
      tension: 0.1
    }]
  };
  
  // Create chart
  const ctx = document.getElementById('myChart').getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: chartData,
    options: {
      scales: {
        x: {
          type: 'time',
          time: { unit: 'hour' }
        },
        y: {
          beginAtZero: false,
          title: { display: true, text: 'Portfolio Value ($)' }
        }
      }
    }
  });
}

displayTeamChart('test1', 'YOUR_API_KEY_HERE');
```

---

### Example 3: Multi-Team Comparison Chart

```javascript
async function displayComparisonChart() {
  // Fetch all teams history
  const response = await fetch('http://localhost:8000/api/v1/leaderboard/history?days=7&limit=500');
  const data = await response.json();
  
  // Create datasets for each team
  const datasets = Object.entries(data.teams).map(([teamId, history], index) => {
    const colors = [
      'rgb(255, 99, 132)',
      'rgb(54, 162, 235)',
      'rgb(75, 192, 192)',
      'rgb(255, 205, 86)',
    ];
    
    return {
      label: teamId,
      data: history.map(h => ({ x: new Date(h.timestamp), y: h.value })),
      borderColor: colors[index % colors.length],
      backgroundColor: colors[index % colors.length] + '33',
      tension: 0.1
    };
  });
  
  const ctx = document.getElementById('comparisonChart').getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      scales: {
        x: { type: 'time', time: { unit: 'day' } },
        y: { title: { display: true, text: 'Portfolio Value ($)' } }
      },
      plugins: {
        title: { display: true, text: 'Team Performance Comparison (Last 7 Days)' }
      }
    }
  });
}

displayComparisonChart();
```

---

### Example 4: Python Client

```python
import requests
import pandas as pd
import matplotlib.pyplot as plt

API_BASE = 'http://localhost:8000'
TEAM_ID = 'test1'
API_KEY = 'your_api_key_here'

# Fetch team history
response = requests.get(
    f'{API_BASE}/api/v1/team/{TEAM_ID}/history',
    params={'key': API_KEY, 'days': 7, 'limit': 1000}
)
data = response.json()

# Convert to DataFrame
df = pd.DataFrame(data['history'])
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)

# Plot
plt.figure(figsize=(12, 6))
plt.plot(df.index, df['value'])
plt.title(f'{TEAM_ID} Portfolio Performance')
plt.xlabel('Date/Time')
plt.ylabel('Portfolio Value ($)')
plt.grid(True)
plt.tight_layout()
plt.show()

# Calculate returns
df['returns'] = df['value'].pct_change()
print(f"Total Return: {(df['value'].iloc[-1] / df['value'].iloc[0] - 1) * 100:.2f}%")
print(f"Mean Daily Return: {df['returns'].mean() * 100:.4f}%")
print(f"Volatility: {df['returns'].std() * 100:.4f}%")
```

---

### Example 5: Fetch and Display Team Metrics

```javascript
async function displayTeamMetrics(teamId, apiKey) {
  // Fetch metrics
  const response = await fetch(
    `http://localhost:8000/api/v1/team/${teamId}/metrics?key=${apiKey}&days=7`
  );
  const data = await response.json();
  const metrics = data.metrics;
  
  // Display in a dashboard
  console.log(`Performance Metrics for ${teamId}:`);
  console.log(`  Sharpe Ratio: ${metrics.sharpe_ratio.toFixed(2)}`);
  console.log(`  Sortino Ratio: ${metrics.sortino_ratio.toFixed(2)}`);
  console.log(`  Calmar Ratio: ${metrics.calmar_ratio.toFixed(2)}`);
  console.log(`  Max Drawdown: ${metrics.max_drawdown_percentage.toFixed(2)}%`);
  console.log(`  Total Return: ${metrics.total_return_percentage.toFixed(2)}%`);
  console.log(`  Win Rate: ${metrics.win_rate_percentage.toFixed(2)}%`);
  console.log(`  Profit Factor: ${metrics.profit_factor.toFixed(2)}`);
  
  // Create metrics cards
  const metricsHTML = `
    <div class="metrics-grid">
      <div class="metric-card">
        <h3>Sharpe Ratio</h3>
        <div class="value ${metrics.sharpe_ratio > 1 ? 'good' : 'poor'}">
          ${metrics.sharpe_ratio.toFixed(2)}
        </div>
        <div class="label">${metrics.sharpe_ratio > 2 ? 'Excellent' : metrics.sharpe_ratio > 1 ? 'Good' : 'Poor'}</div>
      </div>
      <div class="metric-card">
        <h3>Total Return</h3>
        <div class="value ${metrics.total_return > 0 ? 'positive' : 'negative'}">
          ${metrics.total_return_percentage.toFixed(2)}%
        </div>
      </div>
      <div class="metric-card">
        <h3>Max Drawdown</h3>
        <div class="value">${metrics.max_drawdown_percentage.toFixed(2)}%</div>
      </div>
    </div>
  `;
  
  document.getElementById('metrics-container').innerHTML = metricsHTML;
}
```

---

### Example 6: Enhanced Leaderboard with Metrics

```javascript
async function displayMetricsLeaderboard() {
  // Fetch leaderboard with metrics, sorted by Sharpe ratio
  const response = await fetch(
    'http://localhost:8000/api/v1/leaderboard/metrics?days=7&sort_by=sharpe_ratio'
  );
  const data = await response.json();
  
  // Create table
  const tableHTML = `
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Team</th>
          <th>Portfolio Value</th>
          <th>Sharpe Ratio</th>
          <th>Total Return</th>
          <th>Max DD</th>
          <th>Win Rate</th>
        </tr>
      </thead>
      <tbody>
        ${data.leaderboard.map(team => `
          <tr>
            <td>${team.rank}</td>
            <td>${team.team_id}</td>
            <td>$${team.portfolio_value?.toLocaleString() || 'N/A'}</td>
            <td class="${team.sharpe_ratio > 1 ? 'good' : 'poor'}">
              ${team.sharpe_ratio?.toFixed(2) || 'N/A'}
            </td>
            <td class="${team.total_return > 0 ? 'positive' : 'negative'}">
              ${team.total_return_percentage?.toFixed(2) || 'N/A'}%
            </td>
            <td>${team.max_drawdown_percentage?.toFixed(2) || 'N/A'}%</td>
            <td>${team.win_rate_percentage?.toFixed(2) || 'N/A'}%</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  
  document.getElementById('leaderboard').innerHTML = tableHTML;
}
```

---

### Example 7: cURL Commands

```bash
# Get current leaderboard
curl http://localhost:8000/leaderboard

# Get team status (CLI format)
curl http://localhost:8000/YOUR_API_KEY

# Get team historical data
curl "http://localhost:8000/api/v1/team/test1/history?key=YOUR_API_KEY&days=7&limit=500"

# Get team trades
curl "http://localhost:8000/api/v1/team/test1/trades?key=YOUR_API_KEY&limit=50"

# Get team metrics ⭐ NEW
curl "http://localhost:8000/api/v1/team/test1/metrics?key=YOUR_API_KEY&days=7"

# Get leaderboard with metrics, sorted by Sharpe ratio ⭐ NEW
curl "http://localhost:8000/api/v1/leaderboard/metrics?days=7&sort_by=sharpe_ratio"

# Stream live activity
curl http://localhost:8000/activity/stream
```

---

## Frontend Integration

### Complete HTML + JavaScript Example

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QTC Alpha Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .chart-container {
            margin: 30px 0;
            height: 400px;
        }
        .rank {
            font-weight: bold;
            color: #4CAF50;
        }
        .value {
            font-weight: bold;
            color: #2196F3;
        }
        .refresh-info {
            color: #666;
            font-style: italic;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏆 QTC Alpha Trading Leaderboard</h1>
        
        <table id="leaderboard">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Team</th>
                    <th>Portfolio Value</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
        
        <p class="refresh-info">Auto-refreshes every 60 seconds</p>
        
        <h2>📊 Performance Comparison (Last 7 Days)</h2>
        <div class="chart-container">
            <canvas id="performanceChart"></canvas>
        </div>
    </div>
    
    <script>
        const API_BASE = 'http://localhost:8000';
        let performanceChart = null;
        
        // Fetch and display leaderboard
        async function updateLeaderboard() {
            try {
                const response = await fetch(`${API_BASE}/leaderboard`);
                const data = await response.json();
                
                const tbody = document.querySelector('#leaderboard tbody');
                tbody.innerHTML = '';
                
                data.leaderboard.forEach((team, index) => {
                    const row = tbody.insertRow();
                    const value = team.portfolio_value;
                    const valueStr = value != null ? `$${value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : 'N/A';
                    
                    row.innerHTML = `
                        <td class="rank">${index + 1}</td>
                        <td>${team.team_id}</td>
                        <td class="value">${valueStr}</td>
                    `;
                });
            } catch (error) {
                console.error('Error fetching leaderboard:', error);
            }
        }
        
        // Fetch and display performance chart
        async function updatePerformanceChart() {
            try {
                const response = await fetch(`${API_BASE}/api/v1/leaderboard/history?days=7&limit=500`);
                const data = await response.json();
                
                const datasets = Object.entries(data.teams).map(([teamId, history], index) => {
                    const colors = [
                        'rgb(255, 99, 132)',
                        'rgb(54, 162, 235)',
                        'rgb(75, 192, 192)',
                        'rgb(255, 205, 86)',
                        'rgb(153, 102, 255)',
                    ];
                    
                    return {
                        label: teamId,
                        data: history.map(h => ({ x: new Date(h.timestamp), y: h.value })),
                        borderColor: colors[index % colors.length],
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.1,
                        pointRadius: 0,
                        pointHoverRadius: 5
                    };
                });
                
                const ctx = document.getElementById('performanceChart');
                
                if (performanceChart) {
                    performanceChart.destroy();
                }
                
                performanceChart = new Chart(ctx, {
                    type: 'line',
                    data: { datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                type: 'time',
                                time: {
                                    unit: 'day',
                                    displayFormats: { day: 'MMM d' }
                                },
                                title: { display: true, text: 'Date' }
                            },
                            y: {
                                beginAtZero: false,
                                title: { display: true, text: 'Portfolio Value ($)' },
                                ticks: {
                                    callback: function(value) {
                                        return '$' + value.toLocaleString();
                                    }
                                }
                            }
                        },
                        plugins: {
                            legend: { display: true, position: 'top' },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return context.dataset.label + ': $' + context.parsed.y.toLocaleString();
                                    }
                                }
                            }
                        }
                    }
                });
            } catch (error) {
                console.error('Error fetching performance data:', error);
            }
        }
        
        // Auto-refresh every 60 seconds
        setInterval(updateLeaderboard, 60000);
        setInterval(updatePerformanceChart, 60000);
        
        // Initial load
        updateLeaderboard();
        updatePerformanceChart();
    </script>
</body>
</html>
```

Save this as `index.html` and open in a browser. It will display:
- Live leaderboard table (auto-refreshes)
- Multi-team performance chart
- Professional styling

---

## Rate Limits & Best Practices

### Recommended Polling Intervals

| Endpoint | Recommended Interval | Max Frequency |
|----------|---------------------|---------------|
| `/leaderboard` | 60 seconds | 10 seconds |
| `/api/v1/leaderboard/history` | 60 seconds | 30 seconds |
| `/api/v1/team/{team_id}/history` | 60 seconds | 30 seconds |
| `/activity/stream` | Keep connection open | N/A (SSE) |

### Best Practices

1. **Use SSE for real-time updates** instead of polling `/activity/recent`
2. **Cache historical data** - it doesn't change once written
3. **Limit data points** - use the `limit` parameter to reduce payload size
4. **Handle errors gracefully** - API may be unavailable during restarts
5. **Don't expose API keys in public frontend code** - use backend proxy for team-specific data

### Performance Tips

- Request only the data you need (use `days` and `limit` parameters)
- For charts, 500-1000 data points is usually sufficient
- Historical data older than 1 day is cached in parquet files (faster)
- Use compression (gzip) if your client supports it

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Invalid or missing API key |
| 404 | Not Found | Team ID or endpoint doesn't exist |
| 500 | Server Error | Internal server error |

### Error Response Format

```json
{
  "detail": "Invalid API key"
}
```

### Example Error Handling (JavaScript)

```javascript
async function fetchTeamData(teamId, apiKey) {
  try {
    const response = await fetch(
      `${API_BASE}/api/v1/team/${teamId}/history?key=${apiKey}&days=7`
    );
    
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Invalid API key');
      } else if (response.status === 404) {
        throw new Error('Team not found');
      } else {
        throw new Error(`Server error: ${response.status}`);
      }
    }
    
    const data = await response.json();
    return data;
    
  } catch (error) {
    console.error('Failed to fetch team data:', error);
    // Show user-friendly error message
    alert(`Error: ${error.message}`);
    return null;
  }
}
```

---

## Quick Reference

### Public Endpoints (No Auth)
```
GET  /leaderboard                          # Current rankings
GET  /api/v1/leaderboard/history           # All teams historical data
GET  /api/v1/leaderboard/metrics           # Leaderboard with performance metrics ⭐ NEW
GET  /activity/recent                      # Recent activity log
GET  /activity/stream                      # Live activity stream (SSE)
```

### Team Endpoints (Require API Key)
```
GET  /line/{team_key}                      # Team status (JSON)
GET  /{team_key}                           # Team status (plain text)
GET  /api/v1/team/{team_id}/history        # Team historical data
GET  /api/v1/team/{team_id}/trades         # Team trade history
GET  /api/v1/team/{team_id}/metrics        # Team performance metrics ⭐ NEW
```

### Testing the API

```bash
# Test leaderboard
curl http://localhost:8000/leaderboard | jq

# Test team history (replace with your key)
curl "http://localhost:8000/api/v1/team/test1/history?key=YOUR_KEY&days=7" | jq

# Test with httpie (prettier output)
http GET http://localhost:8000/leaderboard
```

---

## Support & Questions

For issues or questions:
1. Check the logs: `qtc_alpha.log` and `qtc_alpha_errors.log`
2. Verify API server is running: `ps aux | grep uvicorn`
3. Test endpoints with `curl` or browser DevTools
4. Check CORS settings if accessing from browser

**Start API Server:**
```bash
cd /opt/qtc
uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload
```

**Access API Documentation (FastAPI Auto-Docs):**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

**Happy Trading! 📈**

