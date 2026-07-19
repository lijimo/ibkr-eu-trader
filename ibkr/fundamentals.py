"""Fundamentals via IBKR's own ``reqFundamentalData`` (Reuters-sourced XML) —
deliberately not a second data vendor. Coverage and entitlement depend on
your IBKR account's market data subscriptions: some report types are
included with a standard account, others (especially ``ReportsFinStatements``
and ``RESC``) may require a paid Reuters Fundamentals subscription or may
simply be unavailable for a given symbol. This module does not parse the XML
into a fixed schema — Reuters' fundamentals XML is large and report-type
specific, so the raw XML is returned as-is for the caller (typically the
agent) to read directly, rather than pretending to extract a fixed set of
fields that may not exist for every report type or every symbol.
"""

from __future__ import annotations

from typing import Any

from ibkr.connection import IBKRConfig, IBKRConnectionError, pool
from ibkr.contracts import make_contract, qualify_contract

REPORT_TYPES = frozenset(
    {
        "ReportSnapshot",  # company overview
        "ReportsFinSummary",  # financial summary
        "ReportRatios",  # key ratios
        "ReportsFinStatements",  # full financial statements
        "RESC",  # analyst estimates
        "ReportsOwnership",  # ownership
        "CalendarReport",  # upcoming calendar events
    }
)


def get_fundamentals(
    symbol: str,
    *,
    config: IBKRConfig | None = None,
    exchange: str = "IBIS",
    currency: str = "EUR",
    sec_type: str = "STK",
    report_type: str = "ReportSnapshot",
) -> dict[str, Any]:
    """Fetch a raw fundamentals XML report for a symbol via IBKR.

    Raises ValueError for an unrecognized report_type rather than passing an
    invalid value through to TWS. Raises IBKRConnectionError if TWS returns
    no data (which usually means the account isn't entitled to this report
    type for this symbol, not a transient failure).
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(f"unknown report_type={report_type!r}; supported: {sorted(REPORT_TYPES)}")

    cfg = config or IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        contract = make_contract(symbol, exchange=exchange, currency=currency, sec_type=sec_type)
        qualify_contract(ib, contract)
        xml = ib.reqFundamentalData(contract, report_type)
    finally:
        pool.release()

    if not xml:
        raise IBKRConnectionError(
            f"no {report_type} data returned for {symbol} — this usually means the "
            "account isn't entitled to this report type (check Reuters Fundamentals "
            "market data subscriptions), not a transient error."
        )

    return {
        "status": "ok",
        "symbol": symbol.upper(),
        "exchange": exchange,
        "currency": currency,
        "report_type": report_type,
        "xml": xml,
    }
