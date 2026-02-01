# QTC Alpha - New Features Guide

**Version:** January 16, 2025  
**Status:** Complete Implementation

---

## 🚀 Overview

This guide covers all the new features and enhancements added to QTC Alpha, providing traders and developers with comprehensive information about the enhanced trading platform capabilities.

---

## 📋 New Features Summary

### 1. Strategy Upload System ⭐
- **Web-based strategy deployment** - No more Git dependencies
- **Multiple upload methods** - Single file, ZIP package, or multiple files
- **Enhanced security validation** - Comprehensive import blacklisting and syntax checking
- **Real-time validation** - Immediate feedback on upload success/failure

### 2. Order Management System ⭐
- **Open order tracking** - Monitor pending limit orders
- **Order details** - View comprehensive order information
- **Order cancellation** - Cancel pending orders via API
- **Order status monitoring** - Track order execution progress

### 3. Error Tracking & Debugging ⭐
- **Strategy execution errors** - Monitor runtime exceptions and timeouts
- **Error categorization** - TimeoutError, KeyError, ValidationError, etc.
- **Error history** - Track error patterns over time
- **Debugging support** - Detailed error messages and context

### 4. Execution Health Monitoring ⭐
- **Strategy performance tracking** - Monitor execution times and success rates
- **Timeout risk assessment** - Early warning for approaching 5-second limit
- **Execution statistics** - Success rate, average execution time, etc.
- **Health status indicators** - Active, idle, error states

### 5. Detailed Position Tracking ⭐
- **Symbol-specific history** - Track individual position evolution
- **Position summaries** - Aggregate statistics for all symbols
- **Portfolio composition** - Detailed snapshots with all positions
- **Trading frequency analysis** - Monitor position holding patterns

### 6. System Status Monitoring ⭐
- **Real-time system health** - Market status, orchestrator status, data feed health
- **Market hours tracking** - Current market status and trading hours
- **System uptime monitoring** - Track orchestrator and data feed health
- **Public status endpoint** - No authentication required for system status

---

## 🔧 Technical Implementation Details

### Strategy Upload System

**Security Validation:**
- **65+ blocked imports** - Comprehensive blacklist of dangerous modules
- **Syntax checking** - AST parsing to validate Python syntax
- **Builtin blocking** - Prevents use of `open`, `exec`, `eval`, `__import__`
- **File size limits** - 10MB single files, 50MB ZIP, 100MB total extracted
- **Path traversal prevention** - Secure ZIP extraction

**Upload Methods:**
1. **Single File** (`/api/v1/team/{team_id}/upload-strategy`)
2. **ZIP Package** (`/api/v1/team/{team_id}/upload-strategy-package`)
3. **Multiple Files** (`/api/v1/team/{team_id}/upload-multiple-files`)

### Order Management

**Endpoints:**
- `GET /api/v1/team/{team_id}/orders/open` - List open orders
- `GET /api/v1/team/{team_id}/orders/{order_id}` - Order details
- `DELETE /api/v1/team/{team_id}/orders/{order_id}` - Cancel order

**Features:**
- Real-time order status updates
- Partial fill tracking
- Order history and details
- Secure order cancellation

### Error Tracking

**Error Types:**
- `TimeoutError` - Strategy execution exceeded 5 seconds
- `KeyError` - Missing data or symbol references
- `ValidationError` - Invalid signal format
- `AttributeError` - Code logic errors
- `ImportError` - Blacklisted import attempts

**Monitoring:**
- Error count and frequency
- Recent error history
- Error categorization
- Debugging context

### Execution Health

**Metrics:**
- Execution success rate
- Average execution time
- Timeout count and risk level
- Strategy status (active/idle/error)
- Signal generation rate

**Health Indicators:**
- `active` - Running and executing normally
- `idle` - Loaded but not executing (outside market hours)
- `error` - Failed to execute, check errors

### Position Tracking

**Symbol-Specific Tracking:**
- Position quantity and value over time
- Entry/exit point analysis
- Holding period statistics
- Position sizing patterns

**Portfolio Composition:**
- Complete position snapshots
- Asset allocation tracking
- Portfolio reconstruction
- Detailed position history

### System Status

**Health Monitoring:**
- Market status (open/closed)
- Orchestrator status (running/stopped)
- Data feed health (healthy/delayed/stale)
- System uptime and heartbeat

**Status Values:**
- `operational` - All systems running normally
- `degraded` - Running but data may be stale
- `stopped` - Orchestrator not running
- `starting` - System initializing

---

## 📚 API Endpoints Reference

### Public Endpoints (No Authentication)
```bash
GET /api/v1/status                    # System health status
GET /leaderboard                      # Current rankings
GET /api/v1/leaderboard/history       # All teams historical data
GET /api/v1/leaderboard/metrics       # Leaderboard with performance metrics
GET /activity/recent                   # Recent activity log
GET /activity/stream                   # Live activity stream (SSE)
```

### Team Endpoints (Require API Key)
```bash
# Basic Team Data
GET /api/v1/team/{team_id}                    # Team status and metrics
GET /api/v1/team/{team_id}/history            # Portfolio value history
GET /api/v1/team/{team_id}/trades             # Trade history
GET /api/v1/team/{team_id}/metrics            # Performance metrics

# Enhanced Monitoring
GET /api/v1/team/{team_id}/execution-health   # Strategy execution health
GET /api/v1/team/{team_id}/errors            # Strategy execution errors
GET /api/v1/team/{team_id}/portfolio-history # Detailed portfolio snapshots

# Position Tracking
GET /api/v1/team/{team_id}/position/{symbol}/history  # Symbol position history
GET /api/v1/team/{team_id}/positions/summary          # Position statistics

# Order Management
GET /api/v1/team/{team_id}/orders/open        # Open orders
GET /api/v1/team/{team_id}/orders/{order_id}  # Order details
DELETE /api/v1/team/{team_id}/orders/{order_id} # Cancel order

# Strategy Upload
POST /api/v1/team/{team_id}/upload-strategy           # Upload single file
POST /api/v1/team/{team_id}/upload-strategy-package   # Upload ZIP package
POST /api/v1/team/{team_id}/upload-multiple-files      # Upload multiple files
```

---

## 🎯 Usage Examples

### Strategy Upload Example

**Single File Upload:**
```bash
curl -X POST "https://api.qtcq.xyz/api/v1/team/epsilon/upload-strategy" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_file=@strategy.py"
```

**ZIP Package Upload:**
```bash
curl -X POST "https://api.qtcq.xyz/api/v1/team/epsilon/upload-strategy-package" \
  -F "key=YOUR_API_KEY" \
  -F "strategy_zip=@strategy_package.zip"
```

### Monitoring Strategy Health

**Check Execution Health:**
```bash
curl "https://api.qtcq.xyz/api/v1/team/epsilon/execution-health?key=YOUR_KEY"
```

**View Recent Errors:**
```bash
curl "https://api.qtcq.xyz/api/v1/team/epsilon/errors?key=YOUR_KEY&limit=20"
```

### Order Management

**List Open Orders:**
```bash
curl "https://api.qtcq.xyz/api/v1/team/epsilon/orders/open?key=YOUR_KEY"
```

**Cancel Order:**
```bash
curl -X DELETE "https://api.qtcq.xyz/api/v1/team/epsilon/orders/abc-123?key=YOUR_KEY"
```

### Position Tracking

**Symbol Position History:**
```bash
curl "https://api.qtcq.xyz/api/v1/team/epsilon/position/AAPL/history?key=YOUR_KEY&days=7"
```

**Position Summary:**
```bash
curl "https://api.qtcq.xyz/api/v1/team/epsilon/positions/summary?key=YOUR_KEY&days=30"
```

### System Monitoring

**System Status:**
```bash
curl "https://api.qtcq.xyz/api/v1/status"
```

---

## 🔒 Security Features

### Import Blacklisting
The system blocks 65+ dangerous modules including:
- **Process Control**: `os`, `subprocess`, `multiprocessing`
- **Network Access**: `socket`, `requests`, `urllib`, `http`
- **File System**: `shutil`, `tempfile`, `pathlib`, `glob`
- **Dynamic Execution**: `importlib`, `exec`, `eval`, `__import__`
- **Serialization**: `pickle`, `shelve`, `marshal`, `dill`
- **System Introspection**: `sys`, `ctypes`, `platform`, `inspect`

### Validation Checks
1. **File type validation** (.py or .zip only)
2. **UTF-8 encoding verification**
3. **Python syntax checking** (AST parsing)
4. **Import blacklist enforcement**
5. **Dangerous builtin blocking**
6. **Path traversal prevention**
7. **File size validation**
8. **ZIP bomb protection**

### Rate Limiting
- **Upload endpoints**: 2-3 requests per minute per IP
- **Heavy computation endpoints**: 10-30 requests per minute
- **Standard endpoints**: 60-120 requests per minute
- **Global safety net**: 100 requests per minute

---

## 📊 Performance Metrics

### Execution Health Metrics
- **Success Rate**: Percentage of successful strategy executions
- **Average Execution Time**: Mean time for strategy execution
- **Timeout Risk**: Assessment of approaching 5-second limit
- **Signal Rate**: Frequency of trade signal generation

### Position Tracking Metrics
- **Times Held**: Number of minutes position was held
- **Max Quantity**: Largest position size ever held
- **Average Quantity**: Average position size when holding
- **Current P&L**: Realized and unrealized profit/loss

### System Health Metrics
- **Uptime Status**: System availability and health
- **Data Feed Status**: Freshness and reliability of market data
- **Market Status**: Current trading session status
- **Orchestrator Status**: Trading engine health

---

## 🚀 Getting Started

### For New Users
1. **Read the main documentation** - Start with [README.md](README.md)
2. **Understand the system** - Review [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)
3. **Learn the API** - Study [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
4. **Develop your strategy** - Use [strategy_starter/README.md](strategy_starter/README.md)
5. **Upload and monitor** - Follow this guide for new features

### For Existing Users
1. **Review new endpoints** - Check the API reference above
2. **Update your monitoring** - Use new health and error tracking endpoints
3. **Migrate to web upload** - Move from Git-based to web-based strategy deployment
4. **Enhance your dashboards** - Add position tracking and order management

---

## 📞 Support & Resources

### Documentation
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Complete API reference
- [TRADER_HANDBOOK.md](TRADER_HANDBOOK.md) - Comprehensive trading guide
- [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) - Quick reference

### Troubleshooting
- Check system status: `GET /api/v1/status`
- Monitor execution health: `GET /api/v1/team/{team_id}/execution-health`
- Review errors: `GET /api/v1/team/{team_id}/errors`
- Check logs: `qtc_alpha.log` and `qtc_alpha_errors.log`

### Rate Limits
- Monitor rate limit headers in API responses
- Implement exponential backoff for 429 errors
- Use appropriate polling intervals (see API documentation)

---

## 🎉 Conclusion

The enhanced QTC Alpha platform now provides comprehensive tools for strategy development, deployment, monitoring, and debugging. With the new features, traders can:

- **Deploy strategies easily** via web interface
- **Monitor execution health** in real-time
- **Track detailed positions** and portfolio composition
- **Manage orders** effectively
- **Debug issues** quickly with error tracking
- **Monitor system health** for optimal performance

All features are fully documented and ready for production use. Happy trading! 📈

---

**Last Updated:** January 16, 2025  
**Maintained by:** QTC Alpha Team
