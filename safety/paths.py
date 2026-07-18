"""Runtime state directory — mandate, halt sentinel, audit ledger, data cache.

All local, all outside the repo (see .gitignore) — this is per-user runtime
state, never committed.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_runtime_root() -> Path:
    """Return the runtime root, creating it if needed.

    Override with the RUNTIME_ROOT environment variable; defaults to
    ``~/.ibkr-eu-trader``.
    """
    override = os.environ.get("RUNTIME_ROOT")
    root = Path(override).expanduser() if override else Path.home() / ".ibkr-eu-trader"
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root
