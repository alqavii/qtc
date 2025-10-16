# QTC Quant Trading Orchestrator

> A production-minded, minute-driven trading orchestrator for QTC. It fetches minute bars, loads user strategies safely, executes trades via Alpaca, logs trades/portfolio histories per team, writes a global account history, and exposes a small HTTP API for teams and a public leaderboard.

---

## 🚀 For Traders

**New to QTC Alpha?** This section covers everything you need to know as a trader using the system.

### Quick Start
1. **Get your team credentials** - You'll receive a team slug (e.g., `team-alpha`) and API key
2. **Monitor your strategy** - Use the API endpoints to track performance and trades
3. **Access market data** - Historical and real-time data is available via REST API
4. **Check the leaderboard** - See how you rank against other teams

### Essential Endpoints
```bash
# Check your team status (replace team-alpha with your team slug)
curl "https://your-domain.com/api/v1/team/team-alpha?key=YOUR_KEY"

# View recent trades
curl "https://your-domain.com/api/v1/team/team-alpha/trades?key=YOUR_KEY&limit=50"

# Get portfolio history
curl "https://your-domain.com/api/v1/team/team-alpha/history?key=YOUR_KEY&days=7"

# Public leaderboard (no key needed)
curl "https://your-domain.com/leaderboard"
```

### Market Data Access
```bash
# Get recent price data
curl "https://your-domain.com/api/v1/market-data/AAPL/recent/100"

# Get data for a specific day
curl "https://your-domain.com/api/v1/market-data/AAPL/day/2025-01-15"

# Get data for a time range
curl "https://your-domain.com/api/v1/market-data/AAPL/range?start=2025-01-15T09:30:00Z&end=2025-01-15T16:00:00Z"
```

### 📖 Complete Trader Guide
For detailed information on strategy development, data access patterns, order construction, and system architecture, see the **[TRADER_HANDBOOK.md](TRADER_HANDBOOK.md)**.

---

## 📚 Documentation

**New to QTC Alpha?** Start here:

- **[DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)** - Quick reference to all documentation
- **[SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)** - Complete system guide with FAQ (rate limits, latency, etc.)
- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** - REST API reference with examples
- **[strategy_starter/README.md](strategy_starter/README.md)** - Strategy development guide

---

## 1) What You Get

- Minute-aligned orchestrator with daily backfill (previous day)
- Strategy plugin system (per-team), restricted imports, 5s timeout, validated outputs only
- Trade execution via Alpaca using client order IDs that embed the team ID
- Per-team data lake: trades, per-minute portfolio snapshots (JSONL), daily folded Parquet, per-minute metrics
- Account-level snapshots from Alpaca each minute (JSONL + folded Parquet) with session metrics
- Read-only API for teams and public leaderboard
- Team API keys auto-generated on startup (if missing)
- Mock data included for quick testing

---

## 2) Repo Structure

```
app/
  adapters/
    alpaca_broker.py         # Trading client wrapper (orders, account, positions)
    parquet_writer.py        # Minute Parquet writer
    ticker_adapter.py        # Fetch latest bars / historical day from Alpaca
  api/
    server.py                # FastAPI server (team status + leaderboard)
  cli/
    team_status.py           # Small client to query team status over HTTP
  config/
    environments.py          # Env config + data/cache paths
    settings.py              # Global universe, timezones
  loaders/
    # git_fetch.py removed - strategies now uploaded via web interface
    strategy_loader.py       # Dynamic import + I/O smoke test + schema check
  models/
    teams.py                 # Team, Portfolio, Position models
    ticker_data.py           # MinuteBar etc.
    trading.py               # StrategySignal, TradeRequest, TradeRecord, PortfolioSnapshot
  performance/
    performance_tracker.py   # In-memory snapshots + metrics (per-team)
  services/
    auth.py                  # API key store (data/api_keys.json)
    caching.py               # Simple in-memory TTL cache
    data_api.py              # Read-only Parquet access for strategies
    minute_service.py        # Minute scheduler + daily backfill support
    trade_executor.py        # Local portfolio updates, Alpaca orders, writers
  telemetry/
    error_handler.py         # Centralized error logging and helpers
    logging_config.py        # Logging bootstrap + handler reset
  main.py                    # Single entrypoint (CLI) + orchestrator

strategy_starter/
  README.md                  # Strategy quickstart
  strategy.py                # Minimal skeleton
  tests/test_strategy.py     # Sanity test for shape

data/                        # Runtime data (created at run-time or seeded for mocks)
  api_keys.json              # { team_id: key }
  team/<team_id>/
    trades.jsonl
    portfolio/
      YYYY-MM-DD.jsonl       # Per-minute snapshots for the day
      portfolio.parquet      # Folded history (daily JSONL ? Parquet)
    metrics.jsonl            # Per-minute metrics
  qtc-alpha/
    metrics.jsonl
    portfolio/
      YYYY-MM-DD.jsonl
      portfolio.parquet

external_strategies/         # Synced strategy repos (from team_registry.yaml)
team_registry.yaml           # Team Git URLs + entry points (optional)
requirements.txt             # Python deps
README.md                    # This file
```

---

## 3) Requirements

- Python 3.12.3
- pip-installable wheels for pandas/pyarrow/scipy/numpy (Linux x86_64 common)
- System: `git` for registry sync, correct time (NTP)
- Alpaca account credentials (paper/live)

---

## 4) Installation

```bash
git clone <repo>
cd QTC-Alpha
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 5) Configuration (env)

Set these in your shell, service unit, or .env:

- `QTC_ENV` = `production` | `development` | `testing`
- `ALPACA_API_KEY`, `ALPACA_API_SECRET` (required to trade/fetch)
- `ALPACA_PAPER` = `true` (default) or `false`
- `ADMIN_API_KEY` (optional; no longer needed for public leaderboard)

Data/paths come from `EnvironmentConfig`:
- Data root: `config.get_data_path()` defaults to `./data` in the repo working dir

---

## 6) Running The Orchestrator (single entrypoint)

Two ways to load teams:

A) From a registry file (Git sync)
```bash
python -m app.main --registry team_registry.yaml --sync-registry
```
`team_registry.yaml` example:
```yaml
teams:
  - team_id: team-alpha
    repo_dir: /opt/qtc/external_strategies/team-alpha
    entry_point: strategy:MyStrategy
    initial_cash: 10000
```
- On startup, each team gets an API key in `data/api_keys.json` (existing keys are preserved).
- Strategies are uploaded via web interface and stored in `external_strategies/` and loaded dynamically.

B) From local folders (no Git)
```bash
python -m app.main \
  --teams "Team One;./strategy_starter;strategy:MyStrategy;10000" \
  --teams "Team Two;./strategy_starter;strategy:MyStrategy;150000"
```

Other CLI flags:
- `--duration N`           run for N minutes then stop (graceful)
- `--print-team <team_id>` print latest snapshot/metrics (reads ./data; no run needed)
- `--print-global`         print latest account snapshot/metrics

---

## 7) Strategy Development

Quickstart package: `strategy_starter/`
- Copy into your own repo and set `entry_point: strategy:MyStrategy`
- Implement `generate_signal(team, bars, current_prices) -> dict|None`
- Return a �StrategySignal� dict:
```json
{
  "symbol": "AAPL",
  "action": "buy" | "sell",
  "quantity": 10,
  "price": 150.0,
  "confidence": 0.8,
  "reason": "optional"
}
```

Inputs each minute:
- `team`: `{ id, name, cash, params, api }`
- `bars`: `{ TICKER: { timestamp[], open[], high[], low[], close[], volume[] } }`
- `current_prices`: `{ TICKER: price }`

Read-only Data API for historicals (from Parquet):
```python
api = team["api"]
# single
api.getLastN("AAPL", 200)
api.getDay("AAPL", date(2025,1,15))
api.getRange("AAPL", start_dt, end_dt)
# multi
api.getLastNMulti(["AAPL","MSFT"], 100)
api.getDayMulti(["AAPL","MSFT"], date(2025,1,15))
api.getRangeMulti(["AAPL","MSFT"], start_dt, end_dt)
```

Safety model:
- Only returns are accepted (no side effects)
- Import blacklist: 65 dangerous modules blocked (os, subprocess, requests, socket, pickle, sys, etc.) - all others allowed
- Blocked builtins: `open`, `exec`, `eval`, `__import__`
- File size limits: 10 MB per file, 50 MB for ZIP uploads
- Each call runs in a thread with 5s timeout; errors are logged and isolated by team
- Rate limited: 2-3 uploads per minute per IP

---

## 8) Trading

- Orders go to Alpaca if credentials are set; otherwise, portfolio is updated locally only
- Client order ID embeds team id (e.g., `teamId-YYYYmmddHHMMSSfff`) so broker records never mix between teams

---

## 9) Data Storage Layout

Per team (all paths under `./data` by default):
```
team/<team_id>/
  trades.jsonl                     # one JSON object per executed trade
  portfolio/
    YYYY-MM-DD.jsonl               # per-minute snapshots for the day
    portfolio.parquet              # daily JSONL folded here at UTC day start
  metrics.jsonl                    # per-minute metrics
```

Account level (single Alpaca account):
```
qtc-alpha/
  metrics.jsonl
  portfolio/
    YYYY-MM-DD.jsonl
    portfolio.parquet
```

Minute bars from Alpaca are written separately under:
```
data/prices/minute_bars/y=YYYY/m=M/d=D/minute_bars-<day>.parquet
```

---

## 10) HTTP API (FastAPI)

Start the API server:
```bash
uvicorn app.api.server:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /api/v1/leaderboard` (public)
  - `{ leaderboard: [{ team_id, portfolio_value }] }` sorted desc
- `GET /api/v1/team/{team_id}?key=TEAM_KEY` (per-team auth)
  - `{ team_id, snapshot, metrics }`
- `GET /api/v1/team/{team_id}/line?key=TEAM_KEY` (per-team auth)
  - Plain-text one-liner for CLI display

Team keys:
- Stored in `data/api_keys.json`
- Auto-generated at orchestrator startup for newly created teams; existing keys are preserved

CORS/HTTPS:
- Public leaderboard is keyless
- For browser apps on another domain, add a reverse proxy (e.g., Nginx) or CORS headers

---

## 11) Mock Data Quick Testing

This repo includes rich mock data for 5 teams plus account:
- Keys: `data/api_keys.json`
- Teams: `data/team/<team_id>/`
- Global: `data/qtc-alpha/`

Try:
```bash
# API server
uvicorn app.api.server:app --host 0.0.0.0 --port 8000

# Leaderboard
curl "http://127.0.0.1:8000/api/v1/leaderboard"

# Team (replace with a key from data/api_keys.json)
curl "http://127.0.0.1:8000/api/v1/team/team-red?key=<TEAM_KEY>"
```

---

## 12) Operations & Deployment Tips

- Run orchestrator and API under systemd (Restart=always), set `WorkingDirectory` to repo root
- Keep `data/` owned by the service user and writable
- Use a reverse proxy with HTTPS for public access; proxy `/api/` to the FastAPI server
- Limit who can reach per-team endpoints or proxy them through an authenticated backend
- Logs: `qtc_alpha.log` (basic), plus error handler file `qtc_alpha_errors.log`

---

## 13) Troubleshooting

- 404 BlobNotFound XML from a static site:
  - Your frontend is calling `/api/...` on the static host. Point it to the API base (e.g., `http://91.98.127.14:8000`) or proxy `/api` at your web server.
- CORS/mixed content errors:
  - Serve API via HTTPS or proxy through your frontend origin; avoid calling `http://` from an `https://` page.
- No team data yet:
  - `snapshot` or `metrics` may be null until the first minute tick.
- Keys missing:
  - Keys are auto-created at orchestrator startup. Or run a Python shell to call `auth_manager.ensureTeamKey(team_id)`.

---

## 14) FAQ

- Can strategies write files or call networks?
  - No. Only allowed imports; no write/network. They return a trade intent we validate and execute.
- Can I host the leaderboard elsewhere?
  - Yes. Use `GET /api/v1/leaderboard` from your UI or proxy it. See CORS notes above.
- How do I add teams?
  - Via `--teams` or `--registry`; keys are auto-generated and stored in `data/api_keys.json`.

---

## 15) License

Proprietary / internal use (adjust as needed).
