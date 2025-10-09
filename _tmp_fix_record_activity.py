from pathlib import Path
path = Path(r"app/telemetry/activity.py")
text = path.read_text(encoding="utf-8")
old = "def record_activity(message: str) -> None:\n    timestamp = datetime.now(timezone.utc).replace(microsecond=0)\n    entry = _add_entry(timestamp, message)\n    try:\n        with open(_ACTIVITY_PATH, \"a\", encoding=\"utf-8\") as f:\n            f.write(f\"{entry.timestamp.isoformat()} | {entry.message}\\n\")\n    except Exception:\n        pass\n\n\n"
new = "def record_activity(message: str) -> None:\n    timestamp = datetime.now(timezone.utc).replace(microsecond=0)\n    entry = _add_entry(timestamp, message)\n    try:\n        with open(_ACTIVITY_PATH, \"a\", encoding=\"utf-8\") as f:\n            f.write(f\"{entry.timestamp.isoformat()} | {entry.message}\\n\")\n    except Exception:\n        pass\n\n\n"
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
