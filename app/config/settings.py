"""
QTC Alpha - Central Configuration and Constants

This module contains all application-wide constants, limits, and configuration values.
All configuration should be imported from this module to maintain a single source of truth.
"""

# ============================================================================
# APPLICATION INFO
# ============================================================================

APP_NAME = "QTC Alpha"
APP_VERSION = "1.0.0"


# ============================================================================
# FILE UPLOAD LIMITS (bytes)
# ============================================================================

MAX_SINGLE_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ZIP_FILE_SIZE = 50 * 1024 * 1024     # 50 MB
MAX_TOTAL_EXTRACTED_SIZE = 100 * 1024 * 1024  # 100 MB


# ============================================================================
# TRADING LIMITS & DEFAULTS
# ============================================================================

DEFAULT_INITIAL_CASH = 10000
MAX_POSITION_SIZE = 10000
MAX_DAILY_TRADES = 100
SLIPPAGE_RATE = 0.001


# ============================================================================
# TIMEOUT SETTINGS (seconds)
# ============================================================================

STRATEGY_EXECUTION_TIMEOUT = 5  # Strategy execution timeout


# ============================================================================
# SERVICE INTERVALS (seconds unless noted)
# ============================================================================

# Data repair service intervals
DATA_REPAIR_INTERVAL_MARKET_HOURS = 15 * 60  # 15 minutes
DATA_REPAIR_INTERVAL_OFF_HOURS = 60 * 60     # 60 minutes

# Order reconciliation interval
ORDER_RECONCILIATION_INTERVAL = 30  # 30 seconds

# Daily registry sync interval
DAILY_REGISTRY_SYNC_INTERVAL = 24 * 60 * 60  # 24 hours


# ============================================================================
# ALPACA API SETTINGS
# ============================================================================

ALPACA_BATCH_SIZE = 200  # Alpaca API batch limit for ticker requests


# ============================================================================
# RATE LIMITING
# ============================================================================

# API rate limits (format: "requests/period")
DEFAULT_RATE_LIMIT = "100/minute"


# ============================================================================
# TICKER UNIVERSE
# ============================================================================
# S&P 500 major stocks - tradable on Alpaca
# This is a curated list of liquid, high-volume stocks
# For a complete S&P 500 list, run generate_sp500_universe.py

TICKER_UNIVERSE = [
    # Technology
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "ORCL", "ADBE",
    "CRM", "CSCO", "ACN", "AMD", "INTC", "IBM", "INTU", "NOW", "TXN", "QCOM",
    "AMAT", "MU", "ADI", "LRCX", "KLAC", "SNPS", "CDNS", "MCHP", "NXPI", "FTNT",

    # Financial Services
    "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "BLK",
    "C", "AXP", "SCHW", "CB", "PGR", "MMC", "AON", "ICE", "CME", "BK",

    # Healthcare
    "UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "BMY",
    "AMGN", "GILD", "VRTX", "CVS", "CI", "ELV", "HCA", "MCK", "COR", "ISRG",

    # Consumer Cyclical
    "AMZN", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "MAR", "CMG",
    "ORLY", "AZO", "GM", "F", "YUM", "DHI", "LEN", "DG", "ROST", "POOL",

    # Communication Services
    "META", "GOOGL", "GOOG", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS", "CHTR",
    "EA", "TTWO", "WBD", "PARA", "OMC", "IPG", "MTCH", "PINS", "SNAP", "SPOT",

    # Consumer Defensive
    "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "GIS",
    "KMB", "STZ", "HSY", "SYY", "KHC", "TSN", "CAG", "K", "CPB", "HRL",

    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",
    "WMB", "KMI", "HES", "DVN", "FANG", "BKR", "EQT", "MRO", "APA", "CTRA",

    # Industrials
    "CAT", "BA", "RTX", "HON", "UPS", "LMT", "GE", "DE", "MMM", "UNP",
    "ADP", "ETN", "GD", "NOC", "TT", "ITW", "CSX", "NSC", "FDX", "WM",

    # Materials
    "LIN", "APD", "SHW", "ECL", "FCX", "NEM", "DD", "DOW", "NUE", "PPG",
    "ALB", "VMC", "MLM", "IFF", "CTVA", "CE", "EMN", "FMC", "MOS", "CF",

    # Real Estate
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "WELL", "DLR", "SPG", "VICI",
    "AVB", "EQR", "INVH", "MAA", "ESS", "ARE", "VTR", "PEAK", "DOC", "BXP",

    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "WEC",
    "PCG", "EIX", "PEG", "ES", "AWK", "DTE", "PPL", "FE", "AEE", "CMS",

    # Popular ETFs (if needed for testing/hedging)
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VEA", "VWO", "AGG", "BND",
]

# Total unique tickers (remove duplicates)
TICKER_UNIVERSE = sorted(list(set(TICKER_UNIVERSE)))

# Ticker universe metadata
TICKER_UNIVERSE_SIZE = len(TICKER_UNIVERSE)
TICKER_UNIVERSE_GENERATED = "2026-01-13"  # Update when regenerating


# ============================================================================
# VALIDATION & SECURITY
# ============================================================================

# Blacklisted imports for user strategies (see loaders/static_check.py)
BLACKLISTED_IMPORTS = {
    "os", "sys", "subprocess", "socket", "http", "urllib", "requests",
    "shutil", "pathlib", "pickle", "shelve", "dbm", "__builtin__", "builtins"
}

# Blacklisted builtins for user strategies
BLACKLISTED_BUILTINS = {
    "open", "exec", "eval", "__import__", "compile", "input"
}


# ============================================================================
# DEBUG & TESTING
# ============================================================================

# Set to False in production
DEBUG_MODE = True

# Save trade history to files
SAVE_TRADES = True


# ============================================================================
# NOTES
# ============================================================================
#
# To generate an updated S&P 500 ticker universe:
#   1. Run: python generate_sp500_universe.py
#   2. Copy the output from sp500_ticker_universe.py to this file
#   3. Update TICKER_UNIVERSE_GENERATED date
#
# To add custom tickers:
#   - Add to TICKER_UNIVERSE list above
#   - Ensure they are tradable on Alpaca
#   - Run tests to verify data availability
#
