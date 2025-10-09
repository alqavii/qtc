from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Dict, Optional

from app.config.environments import config
from pathlib import Path as _P
import secrets


class APIAuth:
    """Simple API key manager for teams and admin.

    Stores team API keys in data/api_keys.json as { team_id: key }.
    Admin key is provided via env ADMIN_API_KEY.
    """

    def __init__(self, key_file: Optional[Path] = None) -> None:
        # Anchor default to repo root to avoid WorkingDirectory surprises
        default_file = _P(__file__).resolve().parents[2] / "data" / "api_keys.json"
        # If a key_file is passed use it; else prefer anchored default; finally fall back to config path
        self.key_file = key_file or (
            default_file
            if default_file.exists()
            else config.get_data_path("api_keys.json")
        )
        self._keys: Dict[str, str] = {}
        self._loaded = False
        self._mtime: float = 0.0

    def _load(self) -> None:
        """Load keys from disk once (initialization)."""
        if self._loaded:
            return
        self._reload_from_disk()
        self._loaded = True

    def _reload_from_disk(self) -> None:
        try:
            if self.key_file.exists():
                self._keys = json.loads(self.key_file.read_text(encoding="utf-8"))
                try:
                    self._mtime = self.key_file.stat().st_mtime
                except Exception:
                    self._mtime = 0.0
            else:
                self._keys = {}
                self._mtime = 0.0
        except Exception:
            self._keys = {}
            self._mtime = 0.0

    def _maybe_reload(self) -> None:
        """Reload keys if the file has changed since last read.

        Keeps long-running API processes in sync without restarts.
        """
        try:
            if self.key_file.exists():
                m = self.key_file.stat().st_mtime
                if not self._loaded or m != self._mtime:
                    self._reload_from_disk()
            else:
                # If file disappeared, clear keys
                if self._keys:
                    self._keys = {}
                    self._mtime = 0.0
        except Exception:
            # Do not crash on reload attempt
            pass

    def getTeamKey(self, team_id: str) -> Optional[str]:
        self._maybe_reload()
        return self._keys.get(team_id)

    def setTeamKey(self, team_id: str, key: str) -> None:
        self._maybe_reload()
        self._keys[team_id] = key
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.write_text(json.dumps(self._keys, indent=2), encoding="utf-8")

    def validateTeam(self, team_id: str, key: str) -> bool:
        self._maybe_reload()
        return self._keys.get(team_id) == key

    def findTeamByKey(self, key: str) -> Optional[str]:
        """Reverse-lookup: return team_id for a given team API key, if any."""
        self._maybe_reload()
        for tid, k in self._keys.items():
            if k == key:
                return tid
        return None

    def validateAdmin(self, provided: Optional[str]) -> bool:
        admin_key = os.getenv("ADMIN_API_KEY")
        return bool(admin_key) and provided == admin_key

    def generateKey(self, team_id: str) -> str:
        """Return existing key for team_id or create, persist, and return one.

        Avoids KeyError on first access and ensures the backing file exists.
        """
        self._maybe_reload()
        key = self._keys.get(team_id)
        if key:
            return key

        key = secrets.token_urlsafe(32)
        self._keys[team_id] = key
        try:
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            self.key_file.write_text(json.dumps(self._keys, indent=2), encoding="utf-8")
            # refresh in-memory view + mtime so future reads see the file
            self._reload_from_disk()
        except Exception:
            # Best effort persistence; still return the key
            pass
        return key


auth_manager = APIAuth()
