"""Read-only market data tools. Safe by construction — nothing here can
place an order, so these need no mandate gate.
"""

from __future__ import annotations

from anthropic import beta_tool

from ibkr import market_data


@beta_tool
def get_quote(symbol: str, exchange: str = "IBIS", currency: str = "EUR") -> dict:
    """Get a live top-of-book quote for a symbol.

    Args:
        symbol: The stock symbol, e.g. SAP.
        exchange: IBKR exchange code. Default IBIS (Xetra). Also supported:
            FWB (Frankfurt), SWB (Stuttgart), SBF (Euronext Paris), AEB
            (Euronext Amsterdam), ENEXT.BE (Euronext Brussels), BVME
            (Borsa Italiana / Milan).
        currency: Contract currency. Default EUR.
    """
    return market_data.get_quote(symbol, exchange=exchange, currency=currency)


@beta_tool
def get_historical_bars(symbol: str, exchange: str = "IBIS", currency: str = "EUR", duration: str = "1 Y") -> dict:
    """Get historical daily OHLCV bars for a symbol.

    Args:
        symbol: The stock symbol, e.g. SAP.
        exchange: IBKR exchange code. Default IBIS (Xetra). Also supported:
            FWB (Frankfurt), SWB (Stuttgart), SBF (Euronext Paris), AEB
            (Euronext Amsterdam), ENEXT.BE (Euronext Brussels), BVME
            (Borsa Italiana / Milan).
        currency: Contract currency. Default EUR.
        duration: IBKR duration string, e.g. "1 Y", "6 M", "30 D".
    """
    df = market_data.get_historical_bars(symbol, exchange=exchange, currency=currency, duration=duration)
    if df.empty:
        return {"status": "error", "error": f"no historical data available for {symbol}"}
    return {
        "status": "ok",
        "symbol": symbol.upper(),
        "bar_count": len(df),
        "first_date": str(df.index.min().date()),
        "last_date": str(df.index.max().date()),
        "last_close": float(df["close"].iloc[-1]),
    }
