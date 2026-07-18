"""Kill switch — a sentinel file's existence, not an in-memory flag.

Checked fresh on every order attempt. ``touch ~/.ibkr-eu-trader/HALT`` from
any process, any script, any human, stops trading immediately — this holds
even if the agent process is wedged or non-cooperating, because it never
depends on that process's state.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from safety.paths import get_runtime_root

HALT_FILENAME = "HALT"


def halt_path() -> Path:
    return get_runtime_root() / HALT_FILENAME


def halt_flag_set() -> bool:
    """Return whether trading is currently halted. Pure filesystem check."""
    return halt_path().exists()


def trip_halt(*, by: str, reason: str) -> Path:
    """Set the kill switch. Atomic write (temp file + rename)."""
    path = halt_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"by={by}\nreason={reason}\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def clear_halt() -> None:
    """Clear the kill switch. No-op if not currently halted."""
    halt_path().unlink(missing_ok=True)
