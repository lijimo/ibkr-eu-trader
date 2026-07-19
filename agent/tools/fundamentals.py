"""Read-only fundamentals tool. Safe by construction — no mandate gate needed."""

from __future__ import annotations

from anthropic import beta_tool

from ibkr import fundamentals


@beta_tool
def get_fundamentals(
    symbol: str,
    exchange: str = "IBIS",
    currency: str = "EUR",
    report_type: str = "ReportSnapshot",
) -> dict:
    """Get a fundamentals report for a symbol from IBKR's Reuters-sourced data.

    Returns raw XML for you to read directly — interpret the relevant fields
    yourself rather than expecting a fixed pre-parsed schema, since report
    contents vary by report_type and by symbol. Coverage depends on the
    connected IBKR account's market data entitlements; a report_type that
    isn't subscribed will come back as an error, not empty data.

    Args:
        symbol: Stock symbol, e.g. SAP.
        exchange: IBKR exchange code. Default IBIS (Xetra). Also supported:
            FWB (Frankfurt), SWB (Stuttgart), SBF (Euronext Paris),
            AEB (Euronext Amsterdam), ENEXT.BE (Euronext Brussels),
            BVME (Borsa Italiana / Milan).
        currency: Contract currency. Default EUR.
        report_type: One of ReportSnapshot (company overview),
            ReportsFinSummary (financial summary), ReportRatios (key ratios),
            ReportsFinStatements (full financial statements), RESC (analyst
            estimates), ReportsOwnership (ownership), CalendarReport
            (upcoming calendar events). Default ReportSnapshot.
    """
    try:
        return fundamentals.get_fundamentals(
            symbol, exchange=exchange, currency=currency, report_type=report_type
        )
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - report to the agent, don't crash the tool loop
        return {"status": "error", "error": str(exc)}
