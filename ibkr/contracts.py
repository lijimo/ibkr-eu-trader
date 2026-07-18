"""Contract qualification, quote snapshots, and FX conversion to EUR.

The mandate's caps are all EUR-denominated (this app is EUR-primary), so any
non-EUR position or quote needs converting. IBKR forex pairs quote EUR as the
base currency against every major currency (EURUSD, EURGBP, EURCHF, ...) —
1 EUR = X <currency> — so converting a foreign-currency amount to EUR is
always "divide by the EURxxx quote", never "multiply", unlike a USD-primary
app which has to special-case which currencies quote USD as the base vs. the
quote side.
"""

from __future__ import annotations

import math
from typing import Any

from ibkr.connection import IBKRConnectionError, _require_ib_async


def make_contract(symbol: str, *, exchange: str = "IBIS", currency: str = "EUR", sec_type: str = "STK") -> Any:
    """Build an ib_async contract. Defaults to Xetra-listed EUR stocks."""
    module = _require_ib_async()
    clean_symbol = symbol.strip().upper()
    if sec_type.strip().upper() == "STK" and hasattr(module, "Stock"):
        return module.Stock(clean_symbol, exchange, currency)
    contract = module.Contract()
    contract.symbol = clean_symbol
    contract.secType = sec_type.strip().upper()
    contract.exchange = exchange
    contract.currency = currency
    return contract


def qualify_contract(ib: Any, contract: Any) -> None:
    try:
        ib.qualifyContracts(contract)
    except Exception as exc:  # noqa: BLE001
        raise IBKRConnectionError(f"Failed to qualify contract {contract}: {exc}") from exc


def wait_for_tick(ib: Any, ticker: Any, *, timeout: float = 5.0, poll_interval: float = 0.1) -> None:
    """Pump the event loop until the snapshot ticker has real data, or give up."""
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if _tick_has_data(ticker):
            return
        if hasattr(ib, "sleep"):
            ib.sleep(poll_interval)


def _tick_has_data(ticker: Any) -> bool:
    for field in ("bid", "ask", "last"):
        value = getattr(ticker, field, None)
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            return True
    return False


def mid_price(ticker: Any) -> float | None:
    """Best available price from a ticker: last, else bid/ask midpoint, else close."""

    def valid(v: Any) -> bool:
        return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) and v > 0

    last = getattr(ticker, "last", None)
    if valid(last):
        return float(last)
    bid, ask = getattr(ticker, "bid", None), getattr(ticker, "ask", None)
    if valid(bid) and valid(ask):
        return (float(bid) + float(ask)) / 2.0
    close = getattr(ticker, "close", None)
    if valid(close):
        return float(close)
    return None


def fx_rate_to_eur(ib: Any, currency: str) -> float:
    """Return the EUR value of 1 unit of ``currency`` via a live IBKR FX quote.

    Raises IBKRConnectionError (never fabricates a rate) if no live quote is
    available — an unconvertible position must fail the mandate check
    closed, not be risk-checked against a wrong or stale rate.
    """
    currency = currency.strip().upper()
    if currency == "EUR":
        return 1.0

    module = _require_ib_async()
    pair = f"EUR{currency}"  # IBKR/FX convention: EUR is the base currency
    if hasattr(module, "Forex"):
        contract = module.Forex(pair)
    else:
        contract = module.Contract()
        contract.symbol, contract.currency = "EUR", currency
        contract.secType = "CASH"
        contract.exchange = "IDEALPRO"

    qualify_contract(ib, contract)
    ticker = ib.reqMktData(contract, "", True, False)
    wait_for_tick(ib, ticker)
    price = mid_price(ticker)
    if price is None or price <= 0:
        raise IBKRConnectionError(f"could not obtain a live FX quote for {pair}")
    return 1.0 / price  # 1 EUR = `price` <currency> -> 1 <currency> = 1/price EUR
