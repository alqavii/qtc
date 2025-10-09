import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
import pandas as pd
from typing import cast
from app.models.ticker_data import MinuteBar


class CacheManager:
    """Manages caching of market data and strategy results"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._memory_cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        
    def _is_expired(self, key: str, ttl_seconds: int = 300) -> bool:
        """Check if cached data is expired"""
        if key not in self._cache_ttl:
            return True
        return datetime.now(timezone.utc) > self._cache_ttl[key] + timedelta(seconds=ttl_seconds)
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Cache a value with TTL"""
        self._memory_cache[key] = value
        self._cache_ttl[key] = datetime.now(timezone.utc)
    
    def get(self, key: str, ttl_seconds: int = 300) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self._memory_cache and not self._is_expired(key, ttl_seconds):
            return self._memory_cache[key]
        return None
    
    def cache_bars(self, bars: List[MinuteBar], symbol: str) -> None:
        """Cache minute bars for a symbol"""
        key = f"bars_{symbol}"
        self.set(key, bars, ttl_seconds=60)  # 1 minute TTL for market data
    
    def get_cached_bars(self, symbol: str) -> Optional[List[MinuteBar]]:
        """Get cached minute bars for a symbol"""
        key = f"bars_{symbol}"
        return self.get(key, ttl_seconds=60)
    
    def cache_strategy_result(self, team_id: str, result: Dict[str, Any]) -> None:
        """Cache strategy execution result"""
        key = f"strategy_{team_id}"
        self.set(key, result, ttl_seconds=300)  # 5 minute TTL for strategy results
    
    def get_cached_strategy_result(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Get cached strategy result"""
        key = f"strategy_{team_id}"
        return self.get(key, ttl_seconds=300)
    
    def save_to_disk(self, data: Dict[str, Any], filename: str) -> None:
        """Save data to disk as JSON"""
        filepath = self.cache_dir / f"{filename}.json"
        with open(filepath, 'w') as f:
            json.dump(data, f, default=str, indent=2)
    
    def load_from_disk(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load data from disk JSON file"""
        filepath = self.cache_dir / f"{filename}.json"
        if filepath.exists():
            with open(filepath, 'r') as f:
                return cast(Dict[str, Any], json.load(f))
        return None
    
    def clear_expired(self) -> None:
        """Clear expired cache entries"""
        now = datetime.now(timezone.utc)
        expired_keys = [
            key for key, expiry in self._cache_ttl.items()
            if now > expiry + timedelta(seconds=300)
        ]
        for key in expired_keys:
            self._memory_cache.pop(key, None)
            self._cache_ttl.pop(key, None)


# Global cache instance
cache_manager = CacheManager()
