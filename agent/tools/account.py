"""Read-only account tools."""

from __future__ import annotations

from anthropic import beta_tool

from ibkr import account


@beta_tool
def get_positions() -> dict:
    """List current IBKR positions."""
    return account.get_positions()


@beta_tool
def get_account_snapshot() -> dict:
    """Get IBKR account balances and metadata."""
    return account.get_account_snapshot()
