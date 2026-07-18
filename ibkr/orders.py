"""Order placement mechanics. Deliberately *not* risk-aware — this module
just talks to TWS. Every call here is expected to arrive via
``safety/gate.py::execute_live_order``, which does all the risk checking
first. Nothing in this file should be called directly from ``agent/``.
"""

from __future__ import annotations

from typing import Any

from ibkr.connection import IBKRConfig, _require_ib_async, pool
from ibkr.contracts import make_contract, qualify_contract


def place_order(
    *,
    config: IBKRConfig | None = None,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: float | None = None,
    exchange: str = "IBIS",
    currency: str = "EUR",
    sec_type: str = "STK",
) -> dict[str, Any]:
    """Submit an order. No risk checking here — see safety/gate.py."""
    cfg = config or IBKRConfig.from_env()
    side_token = side.strip().lower()
    if side_token not in ("buy", "sell"):
        return {"status": "error", "error": "side must be 'buy' or 'sell'"}
    if order_type == "limit" and limit_price is None:
        return {"status": "error", "error": "limit order requires limit_price"}

    module = _require_ib_async()
    ib = pool.acquire(cfg)
    try:
        contract = make_contract(symbol, exchange=exchange, currency=currency, sec_type=sec_type)
        qualify_contract(ib, contract)

        action = "BUY" if side_token == "buy" else "SELL"
        if order_type == "limit":
            order = module.LimitOrder(action, quantity, limit_price)
        else:
            order = module.MarketOrder(action, quantity)

        trade = ib.placeOrder(contract, order)
        _pump_until(ib, lambda: getattr(trade.orderStatus, "status", "") not in ("", "PendingSubmit"))
    except Exception as exc:  # noqa: BLE001 - submission errors are reported, not raised
        return {"status": "error", "error": str(exc)}
    finally:
        pool.release()

    return {
        "status": "ok",
        "order_id": str(getattr(trade.order, "orderId", "")),
        "symbol": symbol.upper(),
        "side": side_token,
        "order_status": str(getattr(trade.orderStatus, "status", "")),
    }


def cancel_order(order_id: str, *, config: IBKRConfig | None = None) -> dict[str, Any]:
    """Cancel an open order by id.

    Uses ``reqAllOpenOrders`` (not ``openTrades``/``openOrders``) — the
    connection pool hands out a fresh connection with a new client id per
    top-level call, and ``openTrades``/``openOrders`` only reflect orders
    *that specific connection* has been told about. This was a real bug
    found and fixed against Vibe-Trading's equivalent connector this
    session: a cancel issued on a different pooled connection than the one
    that placed the order would otherwise silently find nothing.
    """
    cfg = config or IBKRConfig.from_env()
    try:
        target_id = int(order_id)
    except ValueError:
        return {"status": "error", "error": "order_id must be an IBKR numeric order id"}

    ib = pool.acquire(cfg)
    try:
        candidates = _safe_call(ib, "reqAllOpenOrders") or _safe_call(ib, "openTrades") or []
        trade = next((t for t in candidates if getattr(t.order, "orderId", None) == target_id), None)
        if trade is None:
            return {"status": "error", "error": f"no open order found with order_id {target_id}"}
        ib.cancelOrder(trade.order)
        _pump_until(ib, lambda: getattr(trade.orderStatus, "status", "") in _CANCEL_DONE_STATES)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    finally:
        pool.release()

    status = str(getattr(trade.orderStatus, "status", ""))
    return {"status": "ok", "order_id": order_id, "cancelled": status in _CANCEL_DONE_STATES, "order_status": status}


_CANCEL_DONE_STATES = {"Cancelled", "ApiCancelled", "Inactive", "PendingCancel"}


def _safe_call(obj: Any, name: str) -> Any:
    fn = getattr(obj, name, None)
    return fn() if fn is not None else None


def _pump_until(ib: Any, predicate: Any, *, timeout: float = 5.0, poll_interval: float = 0.1) -> None:
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if predicate():
            return
        if hasattr(ib, "sleep"):
            ib.sleep(poll_interval)
