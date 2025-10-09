from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Condition, Event
from typing import Any, Deque, Iterator, List, Optional

_ACTIVITY_PATH = Path("data/activity.log")
_ACTIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ActivityEntry:
    seq: int
    timestamp: datetime
    message: str


_activity: Deque[ActivityEntry] = deque(maxlen=2000)
_activity_cond = Condition()
_activity_seq: int = 0


def _add_entry(timestamp: datetime, message: str) -> ActivityEntry:
    global _activity_seq
    with _activity_cond:
        _activity_seq += 1
        entry = ActivityEntry(seq=_activity_seq, timestamp=timestamp, message=message)
        _activity.append(entry)
        _activity_cond.notify_all()
        return entry


def _bootstrap_from_disk() -> None:
    if not _ACTIVITY_PATH.exists():
        return
    try:
        lines = _ACTIVITY_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for line in lines[-2000:]:
        ts_text, _, msg = line.partition(" | ")
        if not msg and ts_text:
            msg = ts_text
            ts_text = ""
        try:
            ts = datetime.fromisoformat(ts_text) if ts_text else datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)
        _add_entry(ts, msg)


_bootstrap_from_disk()


def record_activity(message: str) -> None:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    entry = _add_entry(timestamp, message)
    try:
        with open(_ACTIVITY_PATH, "a", encoding="utf-8") as f:
            f.write(f"{entry.timestamp.isoformat()} | {entry.message}\n")
    except Exception:
        pass


def get_recent_activity(limit: int = 200) -> List[str]:
    with _activity_cond:
        items = list(_activity)[-limit:]
    return [f"{entry.timestamp.isoformat()} | {entry.message}" for entry in items]


def get_recent_activity_entries(limit: int = 200) -> List[dict[str, Any]]:
    with _activity_cond:
        items = list(_activity)[-limit:]
    return [
        {
            "sequence": entry.seq,
            "timestamp": entry.timestamp.isoformat(),
            "message": entry.message,
        }
        for entry in items
    ]


def subscribe_activity(tail: int = 0, *, stop_event: Optional[Event] = None) -> Iterator[ActivityEntry]:
    with _activity_cond:
        if tail > 0:
            if _activity:
                start_seq = max(_activity[0].seq, _activity_seq - tail + 1)
            else:
                start_seq = max(1, _activity_seq - tail + 1)
        else:
            start_seq = _activity_seq + 1
        current_seq = start_seq
    while True:
        with _activity_cond:
            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                if _activity and current_seq < _activity[0].seq:
                    current_seq = _activity[0].seq
                pending = [entry for entry in _activity if entry.seq >= current_seq]
                if pending:
                    break
                if stop_event is not None:
                    _activity_cond.wait(timeout=0.5)
                else:
                    _activity_cond.wait()
        for entry in pending:
            current_seq = entry.seq + 1
            yield entry
            if stop_event is not None and stop_event.is_set():
                return
