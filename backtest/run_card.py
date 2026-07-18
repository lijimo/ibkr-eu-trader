"""A content-hashed receipt of exactly what config produced exactly what
numbers — the Vibe-Trading idea worth keeping outright. Makes a backtest
result independently verifiable months later instead of a number you have
to trust.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def write_run_card(run_dir: Path, *, config: dict[str, Any], metrics: dict[str, Any]) -> Path:
    payload = {"config": config, "metrics": metrics}
    content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    card = {**payload, "content_sha256": content_hash}
    path = run_dir / "run_card.json"
    path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
