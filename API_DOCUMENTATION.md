# QTC Alpha API Documentation

**Version:** Beta
**Last Updated:** October 15, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
   - [Public Endpoints](#public-endpoints)
   - [Team-Authenticated Endpoints](#team-authenticated-endpoints)
   - [Strategy Upload Endpoints](#strategy-upload-endpoints) ⭐ NEW
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
- **Strategy file uploads** (single file, ZIP packages, or multiple files) ⭐ NEW
- **Error tracking and debugging** (timeouts, exceptions, validation failures) ⭐ NEW
- **Detailed position history** (per-symbol tracking and aggregate summaries) ⭐ NEW

**API Features:**
- RESTful JSON API
- CORS enabled for browser access (GET and POST methods)
- Server-Sent Events for real-time updates
- File upload support for strategy deployment
- Strategy error logging and monitoring
- Comprehensive position tracking
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

#### 2. Get System Status ⭐ NEW
**GET** `/api/v1/status`

Returns system-wide health information including market status, orchestrator status, and data feed health. Essential for monitoring and status banners.

**Authentication:** None required (public endpoint)

**Parameters:** None

**Example Request:**
```
GET /api/v1/status
```

**Response:**
```json
{
  "status": "operational",
  "timestamp": "2025-10-15T15:42:30+00:00",
  "market": {
    "is_open": true,
    "status": "trading"
  },
  "orchestrator": {
    "running": true,
    "last_heartbeat": "2025-10-15T15:42:00+00:00",
    "execution_frequency_seconds": 60,
    "teams_loaded": 9,
    "teams_active": 9,
    "uptime_status": "healthy"
  },
  "data_feed": {
    "last_update": "2025-10-15T15:42:00+00:00",
    "seconds_since_update": 30,
    "status": "healthy",
    "symbols_tracked": 9,
    "bars_received": 9
  }
}
```

**Response Fields:**
- `status` - Overall system status: "operational", "degraded", "stopped", "starting"
- `timestamp` - Current server time (ISO 8601 UTC)
- `market.is_open` - Whether US equity market is currently open
- `market.status` - "trading" or "closed"
- `orchestrator.running` - Whether trading orchestrator is active
- `orchestrator.last_heartbeat` - Last time orchestrator updated status
- `orchestrator.execution_frequency_seconds` - How often strategies execute (60s)
- `orchestrator.teams_loaded` - Total teams in system
- `orchestrator.teams_active` - Teams currently executing (market hours)
- `data_feed.status` - "healthy", "delayed", or "stale"
- `data_feed.seconds_since_update` - Freshness indicator
- `data_feed.symbols_tracked` - Number of symbols being monitored

**Status Values:**
- `operational` - All systems running normally
- `degraded` - Running but data may be stale
- `stopped` - Orchestrator not running
- `starting` - System initializing

**Use Cases:**
- System health monitoring
- Status banner in frontend ("🟢 Market Open | ✅ Trading Active")
- Determine why strategies aren't trading (market closed vs system down)
- Alerting and uptime monitoring
- Troubleshooting

---

#### 3. Get Historical Data for All Teams
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
        "value": 5500.25
      }
    }
  },
  "metrics": {
    "total_trades": 25
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
      "team_id": "test1",
      "timestamp": "2025-10-10T14:30:00+00:00",
      "symbol": "NVDA",
      "side": "buy",
      "quantity": "10.0",
      "requested_price": "500.25",
      "execution_price": "500.25",
      "order_type": "market",
      "broker_order_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    },
    {
      "team_id": "test1",
      "timestamp": "2025-10-10T14:25:00+00:00",
      "symbol": "AAPL",
      "side": "sell",
      "quantity": "5.0",
      "requested_price": "175.50",
      "execution_price": "175.48",
      "order_type": "market",
      "broker_order_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901"
    }
  ]
}
```

**Response Fields:**
- `team_id` - Team identifier
- `count` - Total number of trades returned
- `trades` - Array of trade objects, each containing:
  - `team_id` - Team that executed the trade
  - `timestamp` - Execution timestamp (ISO 8601, UTC)
  - `symbol` - Stock ticker (e.g., "NVDA", "AAPL")
  - `side` - "buy" or "sell"
  - `quantity` - Share quantity (string representation of decimal)
  - `requested_price` - Price requested by the strategy (string)
  - `execution_price` - Actual execution price from broker (string)
  - `order_type` - Order type ("market", "limit", etc.)
  - `broker_order_id` - Alpaca broker order ID (UUID, may be null)

**Important Notes:**
1. **All numeric values are strings** - Parse them in your frontend:
   ```javascript
   const price = parseFloat(trade.execution_price);
   const quantity = parseFloat(trade.quantity);
   const totalValue = price * quantity;
   ```

2. **Trades are ordered most recent first** after reversal

3. **`requested_price` vs `execution_price`** - May differ slightly due to market conditions

**Use Cases:**
- Display trade history table
- Analyze trading patterns
- Track order execution
- Calculate trade costs and P&L

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

#### 11. Get Team Errors ⭐ NEW
**GET** `/api/v1/team/{team_id}/errors`

Returns recent strategy execution errors, timeouts, and validation failures for a team. Essential for debugging strategy issues.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |
| `limit` | integer | 100 | Max errors to return (1-500) |

**Example Request:**
```
GET /api/v1/team/epsilon/errors?key=YOUR_API_KEY&limit=20
```

**Response:**
```json
{
  "team_id": "epsilon",
  "error_count": 5,
  "errors": [
    {
      "timestamp": "2025-10-14T14:30:00+00:00",
      "error_type": "TimeoutError",
      "message": "Strategy execution exceeded 5 seconds",
      "strategy": "Strategy",
      "timeout": true,
      "phase": "signal_generation"
    },
    {
      "timestamp": "2025-10-14T14:28:00+00:00",
      "error_type": "KeyError",
      "message": "'AAPL'",
      "strategy": "Strategy",
      "timeout": false,
      "phase": "signal_generation"
    }
  ]
}
```

**Error Types:**
- `TimeoutError` - Strategy took longer than 5 seconds
- `KeyError` - Missing data or symbol
- `ValidationError` - Invalid signal format
- `AttributeError` - Code logic errors
- `ImportError` - Blacklisted import attempted

**Use Cases:**
- Debug strategy timeouts
- Identify runtime exceptions
- Track validation errors
- Monitor strategy health

---

#### 12. Get Team Execution Health ⭐ NEW
**GET** `/api/v1/team/{team_id}/execution-health`

Returns comprehensive execution health metrics for a team's strategy including success rate, timing performance, error counts, and timeout warnings. Critical for monitoring if your strategy is approaching the 5-second timeout limit.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |

**Example Request:**
```
GET /api/v1/team/admin/execution-health?key=YOUR_API_KEY
```

**Response:**
```json
{
  "team_id": "admin",
  "timestamp": "2025-10-15T15:45:00+00:00",
  "strategy": {
    "entry_point": "strategy:Strategy",
    "repo_path": "/opt/qtc/external_strategies/admin",
    "status": "active",
    "last_uploaded": "2025-10-14T16:50:00+00:00",
    "run_24_7": false
  },
  "execution": {
    "is_active": true,
    "last_execution": "2025-10-15T15:44:00+00:00",
    "seconds_since_last": 35,
    "total_executions_today": 157,
    "successful_executions": 155,
    "failed_executions": 2,
    "success_rate_percentage": 98.73
  },
  "errors": {
    "error_count": 1,
    "timeout_count": 1,
    "last_error": {
      "timestamp": "2025-10-15T14:05:00+00:00",
      "error_type": "TimeoutError",
      "message": "Strategy execution exceeded 5 seconds",
      "timeout": true
    },
    "consecutive_failures": 0
  },
  "performance": {
    "avg_execution_time_ms": 125,
    "approaching_timeout": false,
    "timeout_risk": "low",
    "timeout_limit_seconds": 5
  },
  "trading": {
    "total_trades_today": 52,
    "signal_rate_percentage": 33.12
  }
}
```

**Response Fields:**
- `strategy.status` - "active", "idle", "error"
- `strategy.last_uploaded` - When strategy file was last modified
- `execution.is_active` - Currently executing (respects market hours)
- `execution.success_rate_percentage` - % of successful executions
- `errors.timeout_count` - How many times strategy hit 5s limit
- `errors.last_error` - Most recent error details
- `performance.avg_execution_time_ms` - Average strategy execution time
- `performance.approaching_timeout` - Warning if nearing 5s limit
- `performance.timeout_risk` - "low", "medium", "high" based on timeout count
- `trading.signal_rate_percentage` - How often strategy generates trades

**Strategy Status Values:**
- `active` - Running and executing normally
- `idle` - Loaded but not executing (outside market hours if run_24_7=false)
- `error` - Failed to execute, check errors field

**Timeout Risk Levels:**
- `low` - No timeouts, healthy performance
- `medium` - 1-3 timeouts, approaching limit
- `high` - 4+ timeouts, optimization needed

**Use Cases:**
- Monitor if strategy is actively running
- Check if approaching the 5-second timeout limit
- Track execution success rate
- Identify when strategy was last uploaded
- Debug why strategy stopped trading
- Monitor strategy health dashboard

---

#### 13. Get Portfolio History with Positions ⭐ NEW
**GET** `/api/v1/team/{team_id}/portfolio-history`

Returns complete portfolio snapshots including all position details over time. Unlike `/history` which only returns portfolio value, this endpoint includes all position data for each timestamp.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |
| `days` | integer | 7 | Days to look back (1-365) |
| `limit` | integer | 500 | Max snapshots (1-5000) |

**Example Request:**
```
GET /api/v1/team/epsilon/portfolio-history?key=YOUR_API_KEY&days=7&limit=100
```

**Response:**
```json
{
  "team_id": "epsilon",
  "days": 7,
  "snapshot_count": 2835,
  "snapshots": [
    {
      "timestamp": "2025-10-14T14:30:00+00:00",
      "cash": 95000.0,
      "market_value": 100005.0,
      "positions": {
        "AAPL": {
          "symbol": "AAPL",
          "quantity": 10,
          "side": "buy",
          "value": 1505.0
        },
        "NVDA": {
          "symbol": "NVDA",
          "quantity": 5,
          "side": "buy",
          "value": 3500.0
        }
      }
    }
  ]
}
```

**Use Cases:**
- Portfolio composition charts (pie/stacked area)
- Position timeline visualization
- Entry/exit point analysis
- Detailed portfolio reconstruction
- Asset allocation tracking

---

#### 13. Get Position History for Symbol ⭐ NEW
**GET** `/api/v1/team/{team_id}/position/{symbol}/history`

Track how a specific position evolved over time. Shows quantity and value for one symbol across multiple timestamps.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `symbol` | string (path) | - | Stock symbol (e.g., AAPL, NVDA) |
| `key` | string (query) | - | **Required** Team API key |
| `days` | integer | 7 | Days to look back (1-365) |
| `limit` | integer | 1000 | Max data points (1-10000) |

**Example Request:**
```
GET /api/v1/team/epsilon/position/AAPL/history?key=YOUR_API_KEY&days=7&limit=500
```

**Response:**
```json
{
  "team_id": "epsilon",
  "symbol": "AAPL",
  "days": 7,
  "data_points": 156,
  "history": [
    {
      "timestamp": "2025-10-14T09:30:00+00:00",
      "quantity": 0,
      "value": 0
    },
    {
      "timestamp": "2025-10-14T09:31:00+00:00",
      "quantity": 10,
      "value": 1505.0
    },
    {
      "timestamp": "2025-10-14T14:30:00+00:00",
      "quantity": 10,
      "value": 1510.0
    }
  ]
}
```

**Use Cases:**
- Symbol-specific position tracking
- Entry/exit visualization
- Position value progression for one asset
- Position sizing analysis
- Holding period analysis

---

#### 14. Get Positions Summary ⭐ NEW
**GET** `/api/v1/team/{team_id}/positions/summary`

Get aggregate statistics for all symbols traded by a team. Shows which symbols were held, for how long, current positions, and trading frequency.

**Authentication:** Required (API key)

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `team_id` | string (path) | - | Team identifier |
| `key` | string (query) | - | **Required** Team API key |
| `days` | integer | 30 | Days to analyze (1-365) |

**Example Request:**
```
GET /api/v1/team/epsilon/positions/summary?key=YOUR_API_KEY&days=30
```

**Response:**
```json
{
  "team_id": "epsilon",
  "period_days": 30,
  "symbols_traded": 5,
  "current_positions": 2,
  "symbols": [
    {
      "symbol": "AAPL",
      "currently_holding": true,
      "current_quantity": 10,
      "current_value": 1505.0,
      "current_pnl": 5.0,
      "times_held": 156,
      "minutes_held": 156,
      "max_quantity": 15,
      "avg_quantity": 8.5
    },
    {
      "symbol": "NVDA",
      "currently_holding": false,
      "current_quantity": 0,
      "times_held": 45,
      "minutes_held": 45,
      "max_quantity": 10,
      "avg_quantity": 5.0
    }
  ]
}
```

**Metrics Explained:**
- `times_held` - Number of minutes position was held
- `minutes_held` - Total duration position was active
- `max_quantity` - Largest position size ever held
- `avg_quantity` - Average position size when holding

**Use Cases:**
- Overview of all trading activity
- Identify most traded symbols
- Current positions snapshot
- Trading frequency analysis
- Position concentration analysis

---

### Strategy Upload Endpoints

⭐ **NEW:** Teams can now upload their trading strategies directly via API instead of using GitHub!

#### 11. Upload Single Strategy File
**POST** `/api/v1/team/{team_id}/upload-strategy`

Upload a single `strategy.py` file for simple strategies.

**Authentication:** Required (form field)

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | path | Team identifier |
| `key` | form | Team API key |
| `strategy_file` | file | Python file (.py) |

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/team/epsilon/upload-strategy" \
  -F "key=XkljWYUo_pGcZWi7q6BRX6Z5022Vy1KdyhLd_vGLVcw" \
  -F "strategy_file=@strategy.py"
```

**Example Request (JavaScript):**
```javascript
const formData = new FormData();
formData.append('key', apiKey);
formData.append('strategy_file', file);

const response = await fetch(
  `http://localhost:8000/api/v1/team/${teamId}/upload-strategy`,
  { method: 'POST', body: formData }
);
const result = await response.json();
```

**Success Response:**
```json
{
  "success": true,
  "message": "Strategy uploaded successfully for epsilon",
  "team_id": "epsilon",
  "files_uploaded": ["strategy.py"],
  "path": "/opt/qtc/external_strategies/epsilon",
  "note": "Strategy will be loaded on the next trading cycle"
}
```

**Error Response (Validation Failed):**
```json
{
  "detail": "Validation failed: Disallowed import: requests in strategy.py"
}
```

---

#### 12. Upload Strategy Package (ZIP)
**POST** `/api/v1/team/{team_id}/upload-strategy-package`

Upload a ZIP file containing `strategy.py` and helper modules for complex multi-file strategies.

**Authentication:** Required (form field)

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | path | Team identifier |
| `key` | form | Team API key |
| `strategy_zip` | file | ZIP archive containing Python files |

**ZIP Structure:**
```
strategy_package.zip
├── strategy.py          # Required entry point
├── indicators.py        # Helper module (optional)
├── risk_manager.py      # Helper module (optional)
└── utils.py             # Helper module (optional)
```

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/team/epsilon/upload-strategy-package" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_zip=@strategy_package.zip"
```

**Example Request (Python):**
```python
import requests

with open('strategy_package.zip', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/team/epsilon/upload-strategy-package',
        files={'strategy_zip': f},
        data={'key': 'YOUR_API_KEY'}
    )
    
result = response.json()
print(f"Uploaded {result['file_count']} files")
```

**Success Response:**
```json
{
  "success": true,
  "message": "Strategy package uploaded successfully for epsilon",
  "team_id": "epsilon",
  "files_uploaded": [
    "strategy.py",
    "indicators.py",
    "risk_manager.py",
    "utils.py"
  ],
  "file_count": 4,
  "path": "/opt/qtc/external_strategies/epsilon",
  "validation": {
    "all_files_validated": true,
    "security_checks_passed": true
  },
  "note": "Strategy will be loaded on the next trading cycle"
}
```

---

#### 13. Upload Multiple Files
**POST** `/api/v1/team/{team_id}/upload-multiple-files`

Upload multiple Python files individually (alternative to ZIP).

**Authentication:** Required (form field)

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | path | Team identifier |
| `key` | form | Team API key |
| `files` | files | Multiple Python files (must include strategy.py) |

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/team/epsilon/upload-multiple-files" \
  -F "key=YOUR_API_KEY" \
  -F "files=@strategy.py" \
  -F "files=@indicators.py" \
  -F "files=@utils.py"
```

**Example Request (JavaScript):**
```javascript
const formData = new FormData();
formData.append('key', apiKey);

// Add multiple files
for (const file of fileInput.files) {
  formData.append('files', file);
}

const response = await fetch(
  `http://localhost:8000/api/v1/team/${teamId}/upload-multiple-files`,
  { method: 'POST', body: formData }
);
```

**Success Response:**
```json
{
  "success": true,
  "message": "Multiple files uploaded successfully for epsilon",
  "team_id": "epsilon",
  "files_uploaded": ["strategy.py", "indicators.py", "utils.py"],
  "file_count": 3,
  "path": "/opt/qtc/external_strategies/epsilon",
  "validation": {
    "all_files_validated": true,
    "security_checks_passed": true
  },
  "note": "Strategy will be loaded on the next trading cycle"
}
```

---

#### Security Validation

All uploaded files are automatically validated for security using a **blacklist approach** - you can import any library except those explicitly blocked for security reasons.

**✅ ALLOWED - Import freely:**
- **Data Science:** `numpy`, `pandas`, `scipy`, `scikit-learn`, `statsmodels`
- **Technical Analysis:** `ta`, `ta-lib` (if available)
- **Mathematics:** `math`, `cmath`, `statistics`, `decimal`, `fractions`, `random`
- **Data Structures:** `collections`, `heapq`, `bisect`, `array`, `queue`, `dataclasses`, `enum`, `typing`
- **String/Text:** `string`, `re`, `difflib`, `textwrap`
- **Date/Time:** `datetime`, `time`, `calendar`, `zoneinfo`
- **Algorithms:** `itertools`, `functools`, `operator`, `copy`
- **And most other Python libraries not in the blacklist below**

**❌ BLACKLISTED IMPORTS (65 modules):**

Security risks - these imports will cause your strategy to be rejected:

| Category | Blocked Modules | Reason |
|----------|----------------|---------|
| **Process Control** | `os`, `subprocess`, `multiprocessing` | System access |
| **Dynamic Execution** | `importlib`, `pkgutil`, `runpy`, `code`, `codeop` | Code injection |
| **File System** | `shutil`, `tempfile`, `pathlib`, `glob`, `fnmatch` | Unauthorized file access |
| **Network** | `socket`, `urllib`, `urllib3`, `requests`, `http`, `ftplib`, `smtplib`, `poplib`, `imaplib`, `telnetlib`, `socketserver` | External communication |
| **Serialization** | `pickle`, `shelve`, `marshal`, `dill` | RCE vulnerabilities |
| **System Info** | `sys`, `ctypes`, `cffi`, `platform`, `pwd`, `grp`, `resource` | System introspection |
| **Compiler/AST** | `ast`, `compile`, `dis`, `inspect` | Code manipulation |
| **Database** | `sqlite3`, `dbm` | File system writes |
| **Cloud APIs** | `boto3`, `botocore`, `azure`, `google`, `kubernetes`, `docker` | External services |
| **Web Scraping** | `selenium`, `scrapy` | External access |
| **GUI** | `tkinter`, `pygame` | Resource intensive |
| **Other** | `webbrowser`, `xmlrpc`, `pty`, `tty`, `readline`, `rlcompleter`, `pdb`, `trace`, `traceback`, `warnings`, `logging`, `builtins`, `gc`, `weakref` | Various security/stability |

**❌ BLOCKED BUILTIN FUNCTIONS:**
- `open()` - File I/O
- `exec()` - Dynamic code execution
- `eval()` - Dynamic code evaluation
- `__import__()` - Dynamic imports

**📏 FILE SIZE LIMITS:**
- **Single file upload:** 10 MB maximum
- **ZIP file upload:** 50 MB maximum (compressed)
- **Total extracted:** 100 MB maximum (uncompressed)
- **Individual files in ZIP:** 10 MB each

**⏱️ RATE LIMITS:**
- **Upload endpoints:** 2-3 requests per minute per IP
- **Other endpoints:** See [Rate Limits section](#rate-limits--best-practices)

**🔒 VALIDATION CHECKS:**
1. File type validation (.py or .zip only)
2. UTF-8 encoding verification
3. Python syntax checking (AST parsing)
4. Import blacklist enforcement (rejects dangerous imports)
5. Dangerous builtin blocking (`open`, `exec`, `eval`, `__import__`)
6. Path traversal prevention (for ZIP uploads)
7. File size validation (10 MB/50 MB/100 MB limits)
8. ZIP bomb protection (checks uncompressed size)

**Error Examples:**
```json
// Blacklisted import
{
  "detail": "Validation failed: Blacklisted import: requests in strategy.py"
}

// File too large
{
  "detail": "File too large. Maximum size is 10 MB"
}

// ZIP too large
{
  "detail": "ZIP file too large. Maximum size is 50 MB"
}

// Rate limit exceeded
{
  "error": "Rate limit exceeded: 3 per 1 minute"
}

// Missing strategy.py
{
  "detail": "Strategy validation failed: strategy.py not found in upload"
}

// Path traversal attempt
{
  "detail": "Invalid file path in ZIP: ../../../etc/passwd. Paths must be relative and not use .."
}

// Dangerous builtin
{
  "detail": "Validation failed: Disallowed builtin call 'open' in strategy.py"
}
```

---

#### Multi-File Strategy Example

**strategy.py** (main entry point):
```python
from indicators import calculate_rsi
from risk_manager import RiskManager

class Strategy:
    def __init__(self, **kwargs):
        self.risk = RiskManager()
    
    def generate_signal(self, team, bars, current_prices):
        rsi = calculate_rsi(bars['AAPL']['close'])
        
        if rsi < 30:  # Oversold
            quantity = self.risk.calculate_size(team['cash'], current_prices['AAPL'])
            return {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": quantity,
                "price": current_prices['AAPL']
            }
        return None
```

**indicators.py** (helper module):
```python
import numpy as np

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

**risk_manager.py** (helper module):
```python
class RiskManager:
    def calculate_size(self, cash, price, max_position=0.10):
        max_dollar = cash * max_position
        return max(1, int(max_dollar / price))
```

📄 **For complete upload documentation, see:** [STRATEGY_UPLOAD_API.md](STRATEGY_UPLOAD_API.md)

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

### Enforced Rate Limits

The API enforces rate limits to prevent abuse and ensure fair usage. Limits are applied **per IP address**.

| Endpoint | Method | Rate Limit | Purpose |
|----------|--------|------------|---------|
| `/api/v1/team/{team_id}/upload-strategy` | POST | **3 per minute** | Prevent storage abuse |
| `/api/v1/team/{team_id}/upload-strategy-package` | POST | **2 per minute** | Large file uploads |
| `/api/v1/team/{team_id}/upload-multiple-files` | POST | **2 per minute** | Multiple file uploads |
| `/api/v1/team/{team_id}/portfolio-history` | GET | **20 per minute** | Full portfolio snapshots ⭐ NEW |
| `/api/v1/leaderboard/history` | GET | **10 per minute** | Expensive query (all teams) |
| `/api/v1/leaderboard/metrics` | GET | **10 per minute** | Heavy computation |
| `/api/v1/team/{team_id}/errors` | GET | **30 per minute** | Error tracking ⭐ NEW |
| `/api/v1/team/{team_id}/execution-health` | GET | **60 per minute** | Execution monitoring ⭐ NEW |
| `/api/v1/team/{team_id}/history` | GET | **30 per minute** | Moderate load |
| `/api/v1/team/{team_id}/metrics` | GET | **30 per minute** | Moderate computation |
| `/api/v1/team/{team_id}/trades` | GET | **30 per minute** | File reads |
| `/api/v1/team/{team_id}/position/{symbol}/history` | GET | **30 per minute** | Symbol position tracking ⭐ NEW |
| `/api/v1/team/{team_id}/positions/summary` | GET | **30 per minute** | Position statistics ⭐ NEW |
| `/api/v1/status` | GET | **120 per minute** | System health check ⭐ NEW |
| `/leaderboard` | GET | **60 per minute** | Simple read |
| **All endpoints (default)** | ALL | **100 per minute** | Global safety net |

**Rate Limit Headers:**

Every response includes rate limit headers:
```http
X-RateLimit-Limit: 3
X-RateLimit-Remaining: 2
X-RateLimit-Reset: 1697234567
```

**Rate Limit Exceeded Response:**
```json
HTTP/1.1 429 Too Many Requests
{
  "error": "Rate limit exceeded: 3 per 1 minute"
}
```

### Recommended Polling Intervals

| Endpoint | Recommended Interval | Notes |
|----------|---------------------|-------|
| `/api/v1/status` | 30 seconds | System health monitoring ⭐ NEW |
| `/leaderboard` | 60 seconds | Updates every minute during market hours |
| `/api/v1/leaderboard/history` | 5-10 minutes | Historical data, changes slowly |
| `/api/v1/team/{team_id}/history` | 60 seconds | Team-specific updates |
| `/api/v1/team/{team_id}/execution-health` | 60 seconds | Monitor strategy health ⭐ NEW |
| `/api/v1/team/{team_id}/portfolio-history` | 2-5 minutes | Full snapshots with positions ⭐ NEW |
| `/api/v1/team/{team_id}/errors` | On-demand | Check when debugging issues ⭐ NEW |
| `/api/v1/team/{team_id}/position/{symbol}/history` | 5 minutes | Symbol-specific tracking ⭐ NEW |
| `/api/v1/team/{team_id}/positions/summary` | 5-10 minutes | Aggregate statistics ⭐ NEW |
| `/activity/stream` | Keep connection open | Use SSE, don't poll |

### Best Practices

1. **Respect rate limits** - Check `X-RateLimit-Remaining` header before making requests
2. **Use SSE for real-time updates** instead of polling `/activity/recent`
3. **Cache historical data** - it doesn't change once written
4. **Implement exponential backoff** - When you hit 429, wait before retrying
5. **Limit data points** - Use the `limit` parameter to reduce payload size
6. **Handle errors gracefully** - API may be unavailable during restarts
7. **Don't expose API keys in frontend code** - Use backend proxy for team-specific data
8. **Batch upload attempts** - Don't retry uploads immediately on failure

### Performance Tips

- Request only the data you need (use `days` and `limit` parameters)
- For charts, 500-1000 data points is usually sufficient
- Historical data older than 1 day is cached in parquet files (faster)
- Use compression (gzip) if your client supports it
- Monitor rate limit headers to avoid hitting limits

### Handling Rate Limits in Code

**JavaScript Example:**
```javascript
async function fetchWithRateLimit(url) {
  const response = await fetch(url);
  
  // Check rate limit headers
  const remaining = response.headers.get('X-RateLimit-Remaining');
  const reset = response.headers.get('X-RateLimit-Reset');
  
  if (response.status === 429) {
    const resetTime = new Date(reset * 1000);
    const waitMs = resetTime - Date.now();
    console.log(`Rate limited. Waiting ${waitMs}ms...`);
    await new Promise(resolve => setTimeout(resolve, waitMs));
    return fetchWithRateLimit(url); // Retry
  }
  
  if (remaining && parseInt(remaining) < 3) {
    console.warn(`Rate limit warning: ${remaining} requests remaining`);
  }
  
  return response.json();
}
```

**Python Example:**
```python
import time
import requests

def fetch_with_rate_limit(url):
    response = requests.get(url)
    
    # Check rate limit headers
    remaining = int(response.headers.get('X-RateLimit-Remaining', 999))
    reset = int(response.headers.get('X-RateLimit-Reset', 0))
    
    if response.status_code == 429:
        wait_time = max(reset - time.time(), 60)
        print(f"Rate limited. Waiting {wait_time}s...")
        time.sleep(wait_time)
        return fetch_with_rate_limit(url)  # Retry
    
    if remaining < 3:
        print(f"Rate limit warning: {remaining} requests remaining")
    
    return response.json()
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid parameters, file too large, blacklisted import |
| 401 | Unauthorized | Invalid or missing API key |
| 404 | Not Found | Team ID or endpoint doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded - wait before retrying |
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
GET  /api/v1/status                        # System health status ⭐ NEW
GET  /leaderboard                          # Current rankings
GET  /api/v1/leaderboard/history           # All teams historical data
GET  /api/v1/leaderboard/metrics           # Leaderboard with performance metrics
GET  /activity/recent                      # Recent activity log
GET  /activity/stream                      # Live activity stream (SSE)
```

### Team Endpoints (Require API Key)
```
GET  /line/{team_key}                      # Team status (JSON)
GET  /{team_key}                           # Team status (plain text)
GET  /api/v1/team/{team_id}/history        # Team historical data
GET  /api/v1/team/{team_id}/trades         # Team trade history
GET  /api/v1/team/{team_id}/metrics        # Team performance metrics
GET  /api/v1/team/{team_id}/execution-health           # Execution health & timeout monitoring ⭐ NEW
GET  /api/v1/team/{team_id}/errors         # Strategy execution errors ⭐ NEW
GET  /api/v1/team/{team_id}/portfolio-history          # Full portfolio snapshots with positions ⭐ NEW
GET  /api/v1/team/{team_id}/position/{symbol}/history  # Position history for specific symbol ⭐ NEW
GET  /api/v1/team/{team_id}/positions/summary          # Aggregate position statistics ⭐ NEW
```

### Strategy Upload Endpoints (Require API Key)
```
POST /api/v1/team/{team_id}/upload-strategy            # Upload single strategy.py file
POST /api/v1/team/{team_id}/upload-strategy-package    # Upload ZIP package (multi-file)
POST /api/v1/team/{team_id}/upload-multiple-files      # Upload multiple files individually
```

### Testing the API

```bash
# Test system status
curl http://localhost:8000/api/v1/status | jq

# Test leaderboard
curl http://localhost:8000/leaderboard | jq

# Test team history (replace with your key)
curl "http://localhost:8000/api/v1/team/test1/history?key=YOUR_KEY&days=7" | jq

# Test execution health (NEW)
curl "http://localhost:8000/api/v1/team/admin/execution-health?key=YOUR_KEY" | jq

# Test error tracking (NEW)
curl "http://localhost:8000/api/v1/team/epsilon/errors?key=YOUR_KEY&limit=10" | jq

# Test portfolio history with positions (NEW)
curl "http://localhost:8000/api/v1/team/epsilon/portfolio-history?key=YOUR_KEY&days=7&limit=100" | jq

# Test position history for a symbol (NEW)
curl "http://localhost:8000/api/v1/team/epsilon/position/AAPL/history?key=YOUR_KEY&days=7" | jq

# Test position summary (NEW)
curl "http://localhost:8000/api/v1/team/epsilon/positions/summary?key=YOUR_KEY&days=30" | jq

# Test strategy upload
curl -X POST "http://localhost:8000/api/v1/team/epsilon/upload-strategy" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_file=@strategy.py"

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
5. For strategy upload issues, see [STRATEGY_UPLOAD_API.md](STRATEGY_UPLOAD_API.md)

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

