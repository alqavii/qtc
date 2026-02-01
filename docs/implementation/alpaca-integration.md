# Alpaca Integration Guide

This document covers the integration between QTC Alpha and Alpaca's trading APIs.

---

## API Rate Limits

**Source:** Alpaca API Documentation (as of October 2025)

### Trading API
- **Endpoint Rate Limit:** 200 requests per minute
- **Applies to:**
  - Order placement (`POST /v2/orders`)
  - Order queries (`GET /v2/orders`, `GET /v2/orders/{order_id}`)
  - Account information (`GET /v2/account`)
  - Position queries (`GET /v2/positions`)
- **Note:** This limit applies regardless of subscription plan (including Pro plans)

### Market Data API
- **With Unlimited Plan:** Unlimited API calls
- **Without Unlimited Plan:** Varies by subscription tier
- **Applies to:**
  - Real-time bars (`GET /v2/stocks/bars`, `/v2/crypto/bars`)
  - Latest quotes and trades
  - Historical data queries

### QTC Alpha Usage Pattern
- **Strategy Execution:** Once per minute per team
- **Worst Case:** N teams = N order submissions per minute
- **Capacity:** With 200 req/min limit, platform can support up to ~150 active trading teams safely
- **Data Fetching:** Batch fetches for all symbols at once (1 request per minute)

### Rate Limit Management
1. **Batching:** All market data fetched in single request per minute
2. **Caching:** Team portfolio data cached between updates
3. **Error Handling:** Graceful degradation if rate limit hit
4. **Monitoring:** Log warnings when approaching 80% of limit

---

## Order Types Supported

### Market Orders
- **Description:** Execute immediately at current market price
- **Use Case:** Guaranteed execution, price may vary from requested
- **Alpaca API:** `POST /v2/orders` with `type=market`
- **Platform Support:** ✅ Fully implemented

### Limit Orders
- **Description:** Execute only at specified price or better
- **Use Case:** Price control, execution not guaranteed
- **Alpaca API:** `POST /v2/orders` with `type=limit` and `limit_price`
- **Platform Support:** ✅ Implemented (as of this update)

### Stop Orders (Future)
- **Status:** Not yet implemented
- **Planned:** Future enhancement

---

## Execution Price Retrieval

### Current Implementation
After placing an order with Alpaca:
1. Order submitted via `TradingClient.submit_order()`
2. Order ID returned immediately
3. System queries order details via `TradingClient.get_order_by_id()`
4. Extracts `filled_avg_price` for actual execution price
5. Records execution price in `trades.jsonl` and portfolio snapshots

### Execution Price Fields
- **`requested_price`:** Price requested by strategy
- **`execution_price`:** Actual filled price from Alpaca (or requested price if local-only)
- **`broker_order_id`:** Alpaca order ID for tracking

### Local-Only Mode
If Alpaca credentials not configured:
- Orders execute against local portfolio only
- `execution_price` = `requested_price` (no slippage simulation)
- `broker_order_id` = `null`

---

## Authentication

### Credentials Location
Credentials loaded from (in order of precedence):
1. `$QTC_ALPACA_ENV` environment variable (absolute path)
2. `/etc/qtc-alpha/alpaca.env` (production)
3. `<repo>/etc/qtc-alpha/alpaca.env` (development)

### Credential Format
```bash
ALPACA_API_KEY=your_api_key_here
ALPACA_API_SECRET=your_api_secret_here
ALPACA_PAPER=true  # Set to false for live trading
```

### Paper Trading vs Live
- **Default:** Paper trading mode (`ALPACA_PAPER=true`)
- **Paper Trading URL:** https://paper-api.alpaca.markets
- **Live Trading URL:** https://api.alpaca.markets
- **Recommendation:** Always test strategies in paper mode first

---

## Client Order IDs

### Format
```
{team_id}-{timestamp}
```

Example: `epsilon-20251015143055123456`

### Purpose
- Prevents order mixing between teams
- Enables order tracking and debugging
- Required for multi-tenant architecture
- Alpaca supports this via `client_order_id` field

---

## Error Handling

### Order Submission Failures
If Alpaca order submission fails:
1. Error logged with full details
2. Local portfolio still updated (dual-write pattern)
3. Trade record includes `broker_error` in activity log
4. Team continues trading on next cycle

### Rate Limit Exceeded
- Alpaca returns `429 Too Many Requests`
- System logs warning
- Order retried on next minute cycle
- Teams notified via error tracking endpoint

---

## Strategy Signal Format

Strategies return signals with the following structure:

```python
{
    "symbol": "AAPL",           # Required: Stock ticker or crypto symbol
    "action": "buy",            # Required: "buy" or "sell"
    "quantity": 10,             # Required: Number of shares (supports fractional)
    "price": 150.50,            # Required: Reference/limit price
    "order_type": "market",     # Optional: "market" (default) or "limit"
    "time_in_force": "day"      # Optional: "day" (default), "gtc", "ioc", "fok"
}
```

### Supported Symbols
- **Stocks**: `"AAPL"`, `"GOOGL"`, `"TSLA"`, etc.
- **Cryptocurrencies**: `"BTC"`, `"ETH"`, `"SOL"`, etc. (automatically converted to `BTC/USD`, `ETH/USD`, etc.)

### Market Order Example
```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.50,           # Reference price, actual execution may vary
    "order_type": "market"     # Executes immediately
}
```

### Limit Order Example
```python
return {
    "symbol": "AAPL",
    "action": "buy",
    "quantity": 10,
    "price": 150.00,           # Will only buy at $150.00 or less
    "order_type": "limit",
    "time_in_force": "gtc"     # Keep order active until filled
}
```

### Crypto Trading Examples

#### Crypto Market Order
```python
return {
    "symbol": "BTC",           # Automatically converted to BTC/USD
    "action": "buy",
    "quantity": 0.1,           # Fractional crypto amounts supported
    "price": 50000.00,        # Reference price
    "order_type": "market"     # Executes immediately at market price
}
```

#### Crypto Limit Order
```python
return {
    "symbol": "ETH",           # Automatically converted to ETH/USD
    "action": "sell",
    "quantity": 0.5,
    "price": 3000.00,         # Will only sell at $3000.00 or higher
    "order_type": "limit",
    "time_in_force": "gtc"     # Good until cancelled (24/7 crypto trading)
}
```

## Crypto Trading Features

### Automatic Symbol Conversion
- Crypto symbols are automatically converted to Alpaca format
- `"BTC"` → `"BTC/USD"`, `"ETH"` → `"ETH/USD"`, etc.
- No manual symbol formatting required

### 24/7 Trading Support
- Crypto markets trade 24/7 (unlike stock markets)
- Market hours validation automatically allows crypto trading at any time
- Crypto orders use `GTC` (Good Until Cancelled) by default for better 24/7 execution

### Fractional Trading
- Both stocks and crypto support fractional quantities
- Examples: `0.1 BTC`, `0.5 ETH`, `10.5 AAPL`
- Quantities passed as strings to preserve decimal precision

### Supported Cryptocurrencies
The system supports all cryptocurrencies available on Alpaca, including:
- `BTC`, `ETH`, `SOL`, `DOGE`, `XRP`, `ADA`, `LTC`, `BNB`, `DOT`, `AVAX`
- `LINK`, `MATIC`, `ATOM`, `ARB`, `OP`, `BCH`, `ETC`, `NEAR`, `APT`, `TON`
- And any other crypto pairs available on Alpaca

## Best Practices

1. **Always test in paper mode first**
2. **Monitor rate limit usage** via logs
3. **Use limit orders** for price-sensitive strategies
4. **Use market orders** when execution certainty is more important than price
5. **Check market hours** before trading (crypto trades 24/7)
6. **Handle partial fills** appropriately (especially with limit orders)
7. **Log all broker errors** for debugging
8. **Understand time_in_force** implications:
   - Use "day" for intraday stock strategies
   - Use "gtc" for crypto strategies (24/7 trading)
   - Use "ioc"/"fok" for immediate execution requirements
9. **Crypto-specific considerations**:
   - Higher volatility requires careful position sizing
   - Consider using limit orders to avoid slippage
   - Monitor crypto-specific market conditions

---

## API Endpoints Used

### Trading Client (`alpaca.trading.client.TradingClient`)
```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

client = TradingClient(api_key, secret_key, paper=True)

# Submit market order
market_order = MarketOrderRequest(
    symbol="AAPL",
    qty="10",
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY
)
order = client.submit_order(market_order)

# Submit limit order
limit_order = LimitOrderRequest(
    symbol="AAPL",
    qty="10",
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY,
    limit_price="150.50"
)
order = client.submit_order(limit_order)

# Get order details
order_details = client.get_order_by_id(order.id)
execution_price = order_details.filled_avg_price

# Get account info
account = client.get_account()

# Get positions
positions = client.get_all_positions()
```

### Data Client (`alpaca.data.historical`)
```python
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestBarRequest

client = StockHistoricalDataClient(api_key, secret_key)

# Get latest bars
request = StockLatestBarRequest(symbol_or_symbols=["AAPL", "GOOGL"])
bars = client.get_stock_latest_bar(request)
```

---

## References

- [Alpaca API Documentation](https://docs.alpaca.markets/docs)
- [Alpaca Python SDK (alpaca-py)](https://github.com/alpacahq/alpaca-py)
- [Rate Limit Discussion](https://forum.alpaca.markets/t/hitting-rate-limit-fetching-account-even-tho-pro-plan/5574)
- [Order Types Guide](https://docs.alpaca.markets/docs/orders-at-alpaca)

---

**Last Updated:** October 15, 2025

