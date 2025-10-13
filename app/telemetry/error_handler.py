from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class ErrorHandler:
    """Aggregate and persist errors from different subsystems."""

    def __init__(self, log_file: Optional[str] = None, max_recent: int = 50) -> None:
        target = log_file or os.getenv("QTC_ERROR_LOG", "qtc_alpha_errors.log")
        self.log_file = Path(target)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._recent: list[Dict[str, Any]] = []
        self._logger = logging.getLogger("qtc_alpha.errors")
        self._logger.setLevel(logging.ERROR)
        self._formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        self._ensure_file_handler()

    def configure(self, log_file: Optional[str] = None) -> None:
        if not log_file:
            return
        with self._lock:
            self.log_file = Path(log_file)
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_file_handler()

    def handle_data_error(self, error: Exception, *, data_type: Optional[str] = None) -> None:
        self._record("data", error, {"data_type": data_type} if data_type else None)

    def handle_strategy_error(
        self,
        strategy_name: str,
        error: Exception,
        *,
        team_id: Optional[str] = None,
    ) -> None:
        context = {"strategy": strategy_name}
        if team_id:
            context["team_id"] = team_id
        self._record("strategy", error, context)

    def handle_system_error(self, error: Exception, *, component: Optional[str] = None) -> None:
        context = {"component": component} if component else None
        self._record("system", error, context)

    def handle_api_error(
        self,
        error: Exception,
        *,
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        client_ip: Optional[str] = None
    ) -> None:
        """Record an API error with request context.
        
        Args:
            error: The exception that occurred
            endpoint: API endpoint path (e.g., '/api/v1/team/test1/history')
            status_code: HTTP status code (e.g., 400, 401, 500)
            client_ip: IP address of the client making the request
        """
        context = {}
        if endpoint:
            context["endpoint"] = endpoint
        if status_code:
            context["status_code"] = status_code
        if client_ip:
            context["client_ip"] = client_ip
        self._record("api", error, context)

    def get_error_summary(self) -> Dict[str, Any]:
        with self._lock:
            recent = list(self._recent[-50:])
        return {
            "total_errors": len(self._recent),
            "recent_errors": recent,
        }

    def _record(self, category: str, error: Exception, context: Optional[Dict[str, Any]]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "error_type": error.__class__.__name__,
            "message": str(error),
            "context": context or {},
        }
        with self._lock:
            self._recent.append(entry)
        context_str = ", ".join(f"{k}={v}" for k, v in (context or {}).items())
        self._logger.error(
            "%s error: %s%s",
            category,
            error,
            f" ({context_str})" if context_str else "",
            exc_info=True,
        )

    def _ensure_file_handler(self) -> None:
        desired = str(self.log_file.resolve())
        for handler in list(self._logger.handlers):
            if isinstance(handler, logging.FileHandler):
                if str(Path(handler.baseFilename).resolve()) != desired:
                    self._logger.removeHandler(handler)
                    handler.close()
        if not any(
            isinstance(handler, logging.FileHandler)
            and str(Path(handler.baseFilename).resolve()) == desired
            for handler in self._logger.handlers
        ):
            file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            file_handler.setFormatter(self._formatter)
            self._logger.addHandler(file_handler)


default_error_handler = ErrorHandler()
error_handler_instance = default_error_handler

__all__ = [
    "ErrorHandler",
    "default_error_handler",
    "error_handler_instance",
]
