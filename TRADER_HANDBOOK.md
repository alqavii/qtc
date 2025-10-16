# Trader Handbook

This guide walks you through building and delivering your first production-ready strategy for the QTC orchestrator. You will start from `example_strat.py`, learn how to request data, construct compliant orders, and verify that everything is wired up through the API.

## 1. Know Your Starting Point
- `example_strat.py` buys and sells `NVDA` every other minute. It exists purely to demonstrate the interface; do not trade it.
- The orchestrator imports your strategy class, instantiates it once, and calls `generate_signal(team, bars, current_prices)` once per minute.
- Return a trade dict when you want to submit an order; return `None` to skip the minute.

```python
class Strategy:
    def __init__(self, **kwargs):
        ...

    def generate_signal(self, team, bars, current_prices):
        # your logic here
        return None  # or a signal dict built as shown below
```

## 2. Understand the Inputs You Receive
- `team`: lightweight state about your account.
  - Keys: `id` (team slug), `name`, `cash`, `positions`, `params`, and `api`.
  - `params` carries any overrides configured for your team.
- `bars`: minute bars keyed by symbol.
  - Example: `{"AAPL": {"timestamp": [...], "open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]}}`.
  - Bars contain the most recent window the orchestrator has pulled (typically the last trading day plus the current session).
- `current_prices`: latest price per symbol. Use this for mark-to-market logic; fall back to `bars[symbol]["close"][-1]` if needed.

Historical data is available via the helper attached at `team["api"]`:

```python
api = team["api"]
recent = api.getLastN("NVDA", 120)                  # last 120 minutes
day = api.getDay("NVDA", date(2025, 1, 15))         # full trading day
window = api.getRangeMulti(["NVDA", "SPY"], start_dt, end_dt)
```

All helper methods are read-only; they return pandas-like dicts/lists that you can turn into `pandas` DataFrames if you have `pandas` in your repo.

## 3. Constructing a Valid Order
Signals must validate against `StrategySignal`, which enforces:

| Field | Type | Notes |
|-------|------|-------|
| `symbol` | `str` | Must match a ticker the orchestrator can trade. |
| `action` | `"buy"` or `"sell"` | Use `"sell"` for both selling long and entering shorts. |
| `quantity` | `float` (positive) | Shares to buy/sell; fractional OK. |
| `price` | `float` (positive) | Your target price (limit-style). Use the latest price if you want market-like behaviour. |
| `confidence` | `float`, optional | Optional score between 0 and 1 (no enforcement). |
| `reason` | `str`, optional | Short explanation shown in logs. |

Build signals with the provided helper (recommended) or return a plain dict with the same shape:

```python
from example_strat import make_signal

def generate_signal(...):
    symbol = "NVDA"
    price = float(current_prices.get(symbol) or bars[symbol]["close"][-1])
    return make_signal(
        symbol=symbol,
        action="buy",
        quantity=5,
        price=price,
        confidence=0.7,
        reason="Momentum crossover"
    )
```

Tips:
- Always guard against missing data (`bars.get(symbol)` may be `None` right after market open).
- Never return negative or zero quantities/prices; they will fail validation.
- Return `None` to skip placing an order on a given minute.

## 4. Local Testing Workflow
1. Copy `example_strat.py` into your own repo and rename the class or file if you prefer.
2. Run the orchestrator pointing at your strategy:
   ```bash
   python -m app.main --teams "demo-team;./path-to-your-repo;strategy:Strategy;100000" --duration 5
   ```
   This runs for five minutes, feeds your `generate_signal`, and prints any validation errors.
3. Check generated artifacts under `data/team/<team_slug>/` for trades and portfolio snapshots.

## 5. Monitoring via the API (Team Slug Required)
Your team slug is the `team_id` we register (for example, `team-alpha`). You will also receive an API key. Use these to inspect results:

```bash
# Plain-text heartbeat
curl "https://your-domain.com/line/team-alpha?key=YOUR_KEY"

# Detailed JSON snapshot + metrics
curl "https://your-domain.com/api/v1/team/team-alpha?key=YOUR_KEY" | jq

# Portfolio history for the last 7 days
curl "https://your-domain.com/api/v1/team/team-alpha/history?key=YOUR_KEY&days=7" | jq
```

If you just need the public leaderboard (no key required):

```bash
curl "https://your-domain.com/leaderboard" | jq
```

## 6. Delivering Your Strategy Repo
1. **Repository layout**
   - Place your strategy class in a Python file (for example `strategy.py`) and expose it via an entry point string like `strategy:Strategy`.
   - Ensure `__init__.py` is present if you organise code into packages.
   - Include a lightweight `requirements.txt` if you depend on third-party libraries (only allow-listed packages are permitted).
2. **Naming**
   - Keep the repository name aligned with your team slug when possible (e.g., `team-alpha-strategy`).
   - Match the entry point we configure in `team_registry.yaml` (`entry_point: strategy:Strategy` by default). If you change the class name or file name, tell us so we can update the entry point.
3. **Access**
   - Host the repo on GitHub (public or grant read access to our service account). SSH URLs are fine; HTTPS is preferred.
   - Branch default is `main`. If you want us to pull a different branch or a tag, let us know.
4. **Submission**
   - Send us the repo URL, branch (or tag/SHA), and confirm the entry point string.
   - Optional: provide a short README describing your strategy parameters so the operations team can double-check configuration.

## 7. How the Automation Picks Up Your Code
- Nightly sync: every evening the orchestrator runs `sync_all_from_registry`, which shallow-clones the latest commit for each team listed in `team_registry.yaml`.
- If the SHA has not changed since the previous sync, we skip cloning and keep the existing copy.
- After syncing, the loader instantiates your strategy and runs a quick dry-run with dummy data to ensure `generate_signal` validates. If that fails, we quarantine the repo and notify you.
- During trading hours, we call your class every minute; any exceptions are logged but will not stop other teams.

## 8. Checklist Before You Ship
- Strategy returns either `None` or a valid signal dict each minute.
- No blocking network or file writes; stay within the allowed imports.
- You have sensible defaults for quantities and prices.
- Repo builds cleanly with your `requirements.txt`.
- You supplied: repo URL, branch/tag, entry point, and team slug.

Once we add you to `team_registry.yaml`, the nightly pull will fetch your latest commit, and your logic will run automatically in production the next morning.
