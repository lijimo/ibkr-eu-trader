"""Append-only audit ledger — one record per order attempt.

Written after every gate decision (allow, deny, or error) so a logging
failure never blocks a decision, but a decision never goes unlogged. This is
a compliance record, not a cryptographically tamper-evident log — anyone
with filesystem access to the runtime root could edit it. Good enough for a
single-user local tool; don't rely on it as a security control.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from safety.paths import get_runtime_root

AuditOutcome = Literal["allowed", "denied", "error"]


@dataclass(frozen=True)
class AuditEvent:
    kind: Literal["order_placed", "order_cancelled", "order_denied"]
    outcome: AuditOutcome
    symbol: str
    side: str | None
    quantity: float | None
    notional_eur: float | None
    reason: str | None
    broker_response: dict[str, Any] | None = None
    audit_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds"))


def audit_log_path() -> Path:
    return get_runtime_root() / "audit.jsonl"


def write_audit_event(event: AuditEvent) -> None:
    """Append one event to the ledger. Best-effort — never raises to the caller."""
    try:
        path = audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
    except OSError:
        pass
