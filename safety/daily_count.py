"""Per-UTC-day order count, used by the gate to enforce max_trades_per_day.

Deliberately simple (no cross-process file locking) — this is a single-user
local tool, not a multi-worker service. If that ever changes, add an flock
around read-increment-write, mirroring Vibe-Trading's daily_order_lock.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from safety.paths import get_runtime_root


def _count_path() -> Path:
    return get_runtime_root() / "daily_count.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_daily_count() -> int:
    path = _count_path()
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if data.get("date") != _today():
        return 0
    return int(data.get("count", 0))


def increment_daily_count() -> int:
    """Increment and return the new count. Call only after a confirmed ALLOW + successful submit."""
    count = read_daily_count() + 1
    path = _count_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": _today(), "count": count}), encoding="utf-8")
    return count
