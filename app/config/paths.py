"""
QTC Alpha - Path Constants

Centralized path definitions for the entire application.
All file paths should be imported from this module.
"""

from pathlib import Path


# ============================================================================
# ROOT PATHS
# ============================================================================

# Repository root: /home/user/qtc
REPO_ROOT = Path(__file__).resolve().parents[2]

# App root: /home/user/qtc/app
APP_ROOT = REPO_ROOT / "app"


# ============================================================================
# STRATEGY PATHS
# ============================================================================

# External strategies directory
STRATEGY_ROOT = REPO_ROOT / "external_strategies"

# Starter kit for new teams
STARTER_KIT_PATH = REPO_ROOT / "starter_kit"


# ============================================================================
# DATA PATHS
# ============================================================================

# Main data directory
DATA_ROOT = REPO_ROOT / "data"

# Cache directory
CACHE_ROOT = REPO_ROOT / "cache"

# Parquet data storage
PARQUET_ROOT = DATA_ROOT / "parquet"


# ============================================================================
# CONFIG PATHS
# ============================================================================

# Team registry YAML
REGISTRY_PATH = REPO_ROOT / "team_registry.yaml"

# QTC configuration YAML
CONFIG_PATH = DATA_ROOT / "qtc_config.yaml"

# API keys JSON
API_KEYS_PATH = DATA_ROOT / "api_keys.json"

# Alpaca environment file
ALPACA_ENV_PATH = Path("/etc/qtc-alpha/alpaca.env")


# ============================================================================
# LOG PATHS
# ============================================================================

# Logs directory
LOGS_ROOT = REPO_ROOT / "logs"

# Trade logs
TRADE_LOGS_ROOT = LOGS_ROOT / "trades"

# Error logs
ERROR_LOGS_ROOT = LOGS_ROOT / "errors"

# Performance logs
PERFORMANCE_LOGS_ROOT = LOGS_ROOT / "performance"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ensure_directories() -> None:
    """
    Create all necessary directories if they don't exist.
    Should be called at application startup.
    """
    directories = [
        STRATEGY_ROOT,
        DATA_ROOT,
        CACHE_ROOT,
        PARQUET_ROOT,
        LOGS_ROOT,
        TRADE_LOGS_ROOT,
        ERROR_LOGS_ROOT,
        PERFORMANCE_LOGS_ROOT,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def get_team_strategy_path(team_id: str) -> Path:
    """Get the strategy directory path for a given team."""
    return STRATEGY_ROOT / team_id


def get_team_log_path(team_id: str, log_type: str = "trades") -> Path:
    """
    Get the log file path for a given team.

    Args:
        team_id: Team identifier
        log_type: Type of log ("trades", "errors", "performance")

    Returns:
        Path to the team's log file
    """
    if log_type == "trades":
        return TRADE_LOGS_ROOT / f"{team_id}_trades.jsonl"
    elif log_type == "errors":
        return ERROR_LOGS_ROOT / f"{team_id}_errors.jsonl"
    elif log_type == "performance":
        return PERFORMANCE_LOGS_ROOT / f"{team_id}_performance.jsonl"
    else:
        raise ValueError(f"Unknown log type: {log_type}")


def get_cache_path(cache_name: str) -> Path:
    """Get the cache file path for a given cache name."""
    return CACHE_ROOT / f"{cache_name}.cache"


# ============================================================================
# PATH VALIDATION
# ============================================================================

def validate_paths() -> dict[str, bool]:
    """
    Validate that critical paths exist and are accessible.

    Returns:
        Dictionary of path names and their validation status
    """
    validation_results = {
        "repo_root": REPO_ROOT.exists(),
        "app_root": APP_ROOT.exists(),
        "data_root": DATA_ROOT.exists(),
        "cache_root": CACHE_ROOT.exists(),
        "registry": REGISTRY_PATH.exists(),
    }

    return validation_results


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Root paths
    "REPO_ROOT",
    "APP_ROOT",

    # Strategy paths
    "STRATEGY_ROOT",
    "STARTER_KIT_PATH",

    # Data paths
    "DATA_ROOT",
    "CACHE_ROOT",
    "PARQUET_ROOT",

    # Config paths
    "REGISTRY_PATH",
    "CONFIG_PATH",
    "API_KEYS_PATH",
    "ALPACA_ENV_PATH",

    # Log paths
    "LOGS_ROOT",
    "TRADE_LOGS_ROOT",
    "ERROR_LOGS_ROOT",
    "PERFORMANCE_LOGS_ROOT",

    # Utility functions
    "ensure_directories",
    "get_team_strategy_path",
    "get_team_log_path",
    "get_cache_path",
    "validate_paths",
]
