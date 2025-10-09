from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional, Union

_DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _coerce_level(level: Union[str, int]) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        value = getattr(logging, level.upper(), None)
        if isinstance(value, int):
            return value
    raise ValueError(f"Invalid log level: {level}")


def configure_logging(
    level: Union[str, int] = "INFO",
    log_file: Optional[str] = None,
    stream: bool = True,
) -> Path:
    """Configure root logging handlers for CLI/service use."""
    resolved_level = _coerce_level(level)
    target = Path(log_file) if log_file else Path("qtc_alpha.log")
    target.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_DEFAULT_FORMAT)
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = logging.FileHandler(target, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if stream:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    return target
