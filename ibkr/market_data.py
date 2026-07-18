"""Market data reads: live quotes, historical bars, with a local cache for
settled (fully-elapsed) trading days.

IBKR enforces pacing limits on historical-data requests (roughly: no more
than a handful of requests for the same contract/exchange/bar-size within a
couple of seconds, plus an overall budget). Caching settled days avoids
re-fetching data that can never change — only the still-open trading day is
always re-fetched fresh. This is the mitigation called for in the project
plan given IBKR (not a dedicated data vendor) is the primary data source.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ibkr.connection import IBKRConfig, pool
from ibkr.contracts import make_contract, mid_price, qualify_contract, wait_for_tick
from safety.paths import get_runtime_root


def _cache_dir() -> Path:
    d = get_runtime_root() / "cache" / "bars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(symbol: str, exchange: str, currency: str, bar_size: str) -> str:
    return f"{symbol}_{exchange}_{currency}_{bar_size}".replace(" ", "")


def get_quote(
    symbol: str,
    *,
    config: IBKRConfig | None = None,
    exchange: str = "IBIS",
    currency: str = "EUR",
    sec_type: str = "STK",
) -> dict[str, Any]:
    """Fetch a top-of-book quote snapshot. Defaults to Xetra-listed EUR stocks."""
    cfg = config or IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        contract = make_contract(symbol, exchange=exchange, currency=currency, sec_type=sec_type)
        qualify_contract(ib, contract)
        ticker = ib.reqMktData(contract, "", True, False)
        wait_for_tick(ib, ticker)
        return {
            "status": "ok",
            "symbol": symbol.upper(),
            "exchange": exchange,
            "currency": currency,
            "quote": {
                "bid": getattr(ticker, "bid", None),
                "ask": getattr(ticker, "ask", None),
                "last": getattr(ticker, "last", None),
                "mid": mid_price(ticker),
            },
        }
    finally:
        pool.release()


def get_historical_bars(
    symbol: str,
    *,
    config: IBKRConfig | None = None,
    exchange: str = "IBIS",
    currency: str = "EUR",
    sec_type: str = "STK",
    duration: str = "1 Y",
    bar_size: str = "1 day",
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch historical OHLCV bars, using the local settled-day cache when possible.

    Returns a DataFrame indexed by date with columns open/high/low/close/volume.
    """
    key = _cache_key(symbol, exchange, currency, bar_size)
    cache_path = _cache_dir() / f"{key}.csv"

    cached = pd.DataFrame()
    if use_cache and cache_path.exists():
        cached = pd.read_csv(cache_path, index_col="date", parse_dates=True)

    cfg = config or IBKRConfig.from_env()
    ib = pool.acquire(cfg)
    try:
        contract = make_contract(symbol, exchange=exchange, currency=currency, sec_type=sec_type)
        qualify_contract(ib, contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
    finally:
        pool.release()

    rows = [
        {
            "date": getattr(bar, "date", None),
            "open": getattr(bar, "open", None),
            "high": getattr(bar, "high", None),
            "low": getattr(bar, "low", None),
            "close": getattr(bar, "close", None),
            "volume": getattr(bar, "volume", None),
        }
        for bar in bars
    ]
    fresh = pd.DataFrame(rows)
    if not fresh.empty:
        fresh["date"] = pd.to_datetime(fresh["date"])
        fresh = fresh.set_index("date")

    if use_cache and not fresh.empty:
        today = pd.Timestamp(date.today())
        settled = fresh[fresh.index < today]
        combined = pd.concat([cached, settled]) if not cached.empty else settled
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        combined.to_csv(cache_path, index_label="date")

    return fresh if not fresh.empty else cached
