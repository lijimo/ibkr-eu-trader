"""Unit tests for the backtest engine's market allowlist and cost model —
pure logic, only pandas (already a project dependency).
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engine import BacktestConfig, UnsupportedMarketError, run_backtest

pytestmark = pytest.mark.unit


class _AlwaysLongEngine:
    """Signals a full buy on day 2 and holds — enough to trigger one trade."""

    def generate(self, data_map):
        signals = {}
        for symbol, df in data_map.items():
            sig = pd.Series(0.0, index=df.index)
            sig.iloc[1:] = 1.0
            signals[symbol] = sig
        return signals


def _flat_data(prices: list[float]) -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=len(prices), freq="B")
    return {"AAA": pd.DataFrame({"close": prices}, index=dates)}


def test_supported_exchange_accepts_new_venues():
    for exchange in ("SBF", "AEB", "ENEXT.BE", "BVME"):
        cfg = BacktestConfig(exchange=exchange, transaction_tax_pct=0.0)
        assert cfg.exchange == exchange


def test_unsupported_exchange_still_rejected():
    with pytest.raises(UnsupportedMarketError):
        BacktestConfig(exchange="LSE")


def test_french_exchange_requires_explicit_transaction_tax():
    with pytest.raises(UnsupportedMarketError, match="transaction_tax_pct"):
        BacktestConfig(exchange="SBF")


def test_italian_exchange_requires_explicit_transaction_tax():
    with pytest.raises(UnsupportedMarketError, match="transaction_tax_pct"):
        BacktestConfig(exchange="BVME")


def test_german_exchange_does_not_require_transaction_tax():
    cfg = BacktestConfig(exchange="IBIS")  # no transaction_tax_pct passed
    assert cfg.transaction_tax_pct is None


def test_transaction_tax_applied_on_buy_not_on_sell():
    # Price flat at 100 so only the buy leg triggers the FTT; a later forced
    # sell (via a zero-signal day) should not be taxed again.
    data = _flat_data([100.0, 100.0, 100.0])

    class _BuyThenSellEngine:
        def generate(self, data_map):
            df = data_map["AAA"]
            sig = pd.Series([0.0, 1.0, 0.0], index=df.index)
            return {"AAA": sig}

    cfg = BacktestConfig(
        exchange="SBF",
        transaction_tax_pct=0.004,
        commission_min_eur=0.0,
        commission_pct=0.0,
    )
    result = run_backtest(_BuyThenSellEngine(), data, cfg)
    trades = result.trades.set_index("date")

    buy = trades.iloc[0]
    assert buy["shares"] > 0
    assert buy["transaction_tax"] == pytest.approx(buy["shares"] * 100.0 * 0.004)

    sell = trades.iloc[1]
    assert sell["shares"] < 0
    assert sell["transaction_tax"] == pytest.approx(0.0)


def test_commission_uses_max_of_minimum_and_percentage():
    data = _flat_data([100.0, 100.0])
    cfg = BacktestConfig(exchange="IBIS", initial_capital_eur=1_000.0)
    result = run_backtest(_AlwaysLongEngine(), data, cfg)
    trade = result.trades.iloc[0]
    notional = abs(trade["shares"]) * trade["price"]
    assert trade["commission"] == pytest.approx(max(3.0, notional * 0.0005))
