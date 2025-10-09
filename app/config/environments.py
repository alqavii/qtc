from typing import Dict, Any, cast
from pathlib import Path
import os
from app.config.settings import TICKER_UNIVERSE


class EnvironmentConfig:
    """Single unified runtime configuration.

    The constructor accepts an optional `environment` string for backward
    compatibility, but it is ignored. All code runs with one normal config.
    """

    def __init__(self, environment: str | None = None):
        self.environment = environment or "default"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Return the single, unified configuration."""
        return {
            "ticker_universe": TICKER_UNIVERSE,
            "data_dir": "data",
            "cache_dir": "cache",
            "log_level": "INFO",
            "max_position_size": 10000,
            "max_daily_trades": 100,
            "slippage_rate": 0.001,
            "debug_mode": True,
            "save_trades": True,
            "trading_hours": {
                "start": "09:30",
                "end": "16:00",
                "timezone": "America/New_York",
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value: Any = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_trading_hours(self) -> Dict[str, str]:
        return cast(Dict[str, str], self.get("trading_hours", {}))

    def is_trading_time(self) -> bool:
        from datetime import datetime, time
        import pytz

        trading_hours = self.get_trading_hours()
        if not trading_hours:
            return True

        tz = pytz.timezone(trading_hours.get("timezone", "America/New_York"))
        now = datetime.now(tz).time()
        start_time = time.fromisoformat(trading_hours.get("start", "09:30"))
        end_time = time.fromisoformat(trading_hours.get("end", "16:00"))
        return start_time <= now <= end_time

    def get_data_path(self, subpath: str = "") -> Path:
        data_dir = Path(self.get("data_dir", "data"))
        return data_dir / subpath if subpath else data_dir

    def get_cache_path(self, subpath: str = "") -> Path:
        cache_dir = Path(self.get("cache_dir", "cache"))
        return cache_dir / subpath if subpath else cache_dir


# Global configuration instance (no env switching)
config = EnvironmentConfig()
