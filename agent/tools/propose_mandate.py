"""Propose mandate terms for the human to review. This writes a *proposal*,
never a live mandate — only ``cli/commit_mandate.py`` (which the agent
process never imports) can write an actual ``Mandate``. This mirrors
Vibe-Trading's PROPOSE/COMMIT split for exactly the same reason: the agent
can suggest, a human must authorize.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from anthropic import beta_tool

from safety.paths import get_runtime_root


@beta_tool
def propose_mandate(
    max_order_notional_eur: float,
    max_total_exposure_eur: float,
    max_trades_per_day: int,
    exclude_symbols: list[str] | None = None,
    lifetime_days: int = 30,
) -> dict:
    """Propose trading-risk limits for the user to review and commit.

    This does NOT authorize trading — it only writes a proposal file. The
    user must review it and run `commit-mandate` themselves from a terminal
    for it to take effect.

    Args:
        max_order_notional_eur: Suggested max EUR notional for a single order.
        max_total_exposure_eur: Suggested max aggregate EUR position value.
        max_trades_per_day: Suggested max order placements per day.
        exclude_symbols: Symbols to hard-exclude from trading.
        lifetime_days: How many days the mandate should be valid for once committed.
    """
    proposal = {
        "max_order_notional_eur": max_order_notional_eur,
        "max_total_exposure_eur": max_total_exposure_eur,
        "max_trades_per_day": max_trades_per_day,
        "exclude_symbols": exclude_symbols or [],
        "lifetime_days": lifetime_days,
        "proposed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = get_runtime_root() / "mandate_proposal.json"
    path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "ok",
        "proposal_path": str(path),
        "note": (
            "This is a proposal only, not authorization to trade. Review it, then run "
            "`commit-mandate` from a terminal to activate it — the agent cannot do this step."
        ),
    }
