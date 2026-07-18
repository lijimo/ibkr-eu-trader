"""Account and position reads."""

from __future__ import annotations

from typing import Any

from ibkr.connection import IBKRConfig, pool


def get_connected_account_id(config: IBKRConfig | None = None) -> str | None:
    """Return the single managed account id, or None if ambiguous/unavailable.

    The gate uses this for account pinning — a mandate names exactly one
    account, and an order refuses if the connected session isn't that
    account. If TWS reports more than one managed account, this returns
    None (fail-closed) rather than guessing which one the mandate means.
    """
    cfg = config or IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        accounts = _managed_accounts(ib)
    finally:
        pool.release()
    return accounts[0] if len(accounts) == 1 else None


def get_positions(config: IBKRConfig | None = None) -> dict[str, Any]:
    cfg = config or IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        rows = []
        for item in ib.positions():
            contract = item.contract
            rows.append(
                {
                    "account": getattr(item, "account", None),
                    "symbol": getattr(contract, "symbol", None),
                    "sec_type": getattr(contract, "secType", None),
                    "exchange": getattr(contract, "exchange", None),
                    "currency": getattr(contract, "currency", None),
                    "position": getattr(item, "position", None),
                    "avg_cost": getattr(item, "avgCost", None),
                }
            )
        return {"status": "ok", "positions": rows}
    finally:
        pool.release()


def get_account_snapshot(config: IBKRConfig | None = None) -> dict[str, Any]:
    cfg = config or IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        accounts = _managed_accounts(ib)
        summary = [
            {
                "account": getattr(item, "account", None),
                "tag": getattr(item, "tag", None),
                "value": getattr(item, "value", None),
                "currency": getattr(item, "currency", None),
            }
            for item in ib.accountSummary()
        ]
        return {"status": "ok", "accounts": accounts, "summary": summary}
    finally:
        pool.release()


def _managed_accounts(ib: Any) -> list[str]:
    accounts = ib.managedAccounts() if hasattr(ib, "managedAccounts") else []
    if isinstance(accounts, str):
        return [a.strip() for a in accounts.split(",") if a.strip()]
    return [str(a) for a in accounts if a]
