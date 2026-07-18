"""The ONE tool that can move real money. This function is a thin wrapper —
every call routes through ``safety/gate.py::execute_live_order`` and there is
no other path from here to IBKR. Most calls will be denied unless a human
has explicitly committed a mandate via ``commit-mandate`` first.
"""

from __future__ import annotations

from anthropic import beta_tool

from ibkr import account, orders
from ibkr.connection import IBKRConfig
from ibkr.contracts import fx_rate_to_eur, mid_price, qualify_contract, wait_for_tick, make_contract
from ibkr.connection import pool
from safety.gate import OrderIntent, execute_live_order


def _price_eur(symbol: str, *, exchange: str, currency: str) -> float | None:
    """Price a symbol in EUR for the gate's risk math, converting if needed."""
    cfg = IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        contract = make_contract(symbol, exchange=exchange, currency=currency)
        qualify_contract(ib, contract)
        ticker = ib.reqMktData(contract, "", True, False)
        wait_for_tick(ib, ticker)
        price = mid_price(ticker)
        if price is None:
            return None
        rate = fx_rate_to_eur(ib, currency)
        return price * rate
    except Exception:  # noqa: BLE001 - fail closed, gate treats None as unpriceable
        return None
    finally:
        pool.release()


@beta_tool
def place_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: float | None = None,
    exchange: str = "IBIS",
    currency: str = "EUR",
) -> dict:
    """Place a live order on IBKR. Gated by the committed mandate — most
    attempts will be denied unless the user has explicitly authorized
    trading beforehand via `commit-mandate`.

    Args:
        symbol: Stock symbol, e.g. SAP.
        side: 'buy' or 'sell'.
        quantity: Share quantity.
        order_type: 'market' or 'limit'.
        limit_price: Required for limit orders.
        exchange: IBKR exchange code. Default IBIS (Xetra).
        currency: Contract currency. Default EUR.
    """
    connected_account = account.get_connected_account_id()
    if connected_account is None:
        return {
            "status": "error",
            "error": "could not determine a single unambiguous connected IBKR account; refusing",
        }

    intent = OrderIntent(symbol=symbol, side=side, quantity=quantity, order_type=order_type, limit_price=limit_price)
    return execute_live_order(
        intent,
        connected_account_id=connected_account,
        price_eur_fn=lambda s: _price_eur(s, exchange=exchange, currency=currency),
        place_order_fn=lambda **kwargs: orders.place_order(exchange=exchange, currency=currency, **kwargs),
    )


@beta_tool
def cancel_order(order_id: str) -> dict:
    """Cancel an open order by IBKR order id. Not mandate-gated — cancelling
    is risk-reducing, so it's always allowed (subject to the kill switch
    still letting you interact with the account at all, which it does —
    the kill switch only blocks new order placement).

    Args:
        order_id: The IBKR numeric order id to cancel.
    """
    return orders.cancel_order(order_id)
