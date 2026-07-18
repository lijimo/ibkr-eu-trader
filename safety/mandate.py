"""The mandate: an immutable, human-committed record of trading permissions.

Written by exactly one function — ``cli/commit_mandate.py`` — which is never
imported by ``agent/``. The agent process has no code path to construct or
write a ``Mandate``; it can only load and read one that a human already
committed. This is the same non-negotiable boundary Vibe-Trading enforces for
its own mandate system, and for the same reason: even a compromised or
hallucinating model must have zero ability to self-authorize trading
permissions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from safety.paths import get_runtime_root

MANDATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Mandate:
    """Immutable risk-cap contract. One EUR-denominated set of limits — this
    app trades one currency, so there is no asset-class bucketing.

    Attributes:
        schema_version: Must equal MANDATE_SCHEMA_VERSION; the gate refuses
            to operate on an unrecognized version (fail-closed).
        max_order_notional_eur: Max notional (EUR) for a single order.
        max_total_exposure_eur: Max aggregate post-trade market value of all
            open positions, EUR.
        max_trades_per_day: Max order placements per UTC calendar day.
        exclude_symbols: Hard per-symbol denylist. Wins over everything else.
        account_id: The IBKR account this mandate authorizes trading on.
            The gate refuses to place an order on any other connected
            account, even a real one — see ibkr/connection.py.
        created_at: ISO-8601 UTC timestamp of commit.
        expires_at: ISO-8601 UTC timestamp after which the gate fail-closes
            until re-authorized. A mandate must not live forever.
        consent_token_sha256: Hash binding this file to the human commit
            action that produced it (audit trail, not a security boundary).
    """

    schema_version: int
    max_order_notional_eur: float
    max_total_exposure_eur: float
    max_trades_per_day: int
    exclude_symbols: tuple[str, ...]
    account_id: str
    created_at: str
    expires_at: str
    consent_token_sha256: str


def mandate_path() -> Path:
    """Return the path to the committed mandate file."""
    return get_runtime_root() / "mandate.json"


def load_mandate() -> Mandate | None:
    """Load the committed mandate, or ``None`` if none exists / it's invalid.

    Fails closed: any structural problem (missing file, bad JSON, unknown
    schema version, missing field) returns ``None`` rather than raising —
    callers treat ``None`` exactly like "no mandate" (deny).
    """
    path = mandate_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["exclude_symbols"] = tuple(data.get("exclude_symbols", ()))
        mandate = Mandate(**data)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    if mandate.schema_version != MANDATE_SCHEMA_VERSION:
        return None
    return mandate


def is_expired(mandate: Mandate) -> bool:
    """Return True if the mandate has expired (or its expiry can't be parsed — fail-closed)."""
    try:
        expires = datetime.fromisoformat(mandate.expires_at)
    except (ValueError, TypeError):
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= expires


def write_mandate(mandate: Mandate) -> Path:
    """Persist a mandate with owner-only permissions.

    Not called by anything in ``agent/`` — only ``cli/commit_mandate.py``.
    """
    path = mandate_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(mandate), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
