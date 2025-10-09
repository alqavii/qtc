from __future__ import annotations

import re


_slug_pattern = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a human-readable name into a filesystem/API-safe slug."""
    base = name.strip().lower()
    base = _slug_pattern.sub("-", base)
    base = base.strip("-")
    return base or "team"
