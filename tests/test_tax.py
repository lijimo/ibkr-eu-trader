"""Unit tests for the German capital-gains-tax estimate — pure logic, no
IBKR/network dependency, only what the project already depends on (pandas).
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.tax import _compute_realized_gains, estimate_after_tax_returns

pytestmark = pytest.mark.unit


def _trades(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_single_buy_sell_realized_gain():
    trades = _trades(
        {"date": "2026-01-10", "symbol": "SAP", "shares": 10, "price": 100.0, "commission": 3.0},
        {"date": "2026-06-10", "symbol": "SAP", "shares": -10, "price": 150.0, "commission": 3.0},
    )
    realized = _compute_realized_gains(trades)
    assert len(realized) == 1
    # buy commission raises cost basis: avg_cost = (10*100 + 3) / 10 = 100.3
    # sell: (150 - 100.3) * 10 - 3 = 494.0  (both commissions reduce the gain)
    assert realized.iloc[0]["realized_gain_eur"] == pytest.approx(494.0)


def test_multi_symbol_does_not_cross_contaminate_cost_basis():
    trades = _trades(
        {"date": "2026-01-10", "symbol": "SAP", "shares": 10, "price": 100.0, "commission": 3.0},
        {"date": "2026-01-10", "symbol": "SIE", "shares": 5, "price": 200.0, "commission": 3.0},
        {"date": "2026-06-10", "symbol": "SAP", "shares": -10, "price": 150.0, "commission": 3.0},
        {"date": "2026-06-10", "symbol": "SIE", "shares": -5, "price": 180.0, "commission": 3.0},
    )
    realized = _compute_realized_gains(trades)
    assert len(realized) == 2
    sap_gain = realized[realized["symbol"] == "SAP"]["realized_gain_eur"].iloc[0]
    sie_gain = realized[realized["symbol"] == "SIE"]["realized_gain_eur"].iloc[0]
    # buy commission raises cost basis, so both legs' commissions reduce the gain
    sap_avg_cost = (10 * 100.0 + 3.0) / 10
    sie_avg_cost = (5 * 200.0 + 3.0) / 5
    assert sap_gain == pytest.approx((150.0 - sap_avg_cost) * 10 - 3.0)
    assert sie_gain == pytest.approx((180.0 - sie_avg_cost) * 5 - 3.0)


def test_moving_average_cost_basis_on_partial_buys():
    # Buy 10 @ 100 (+3 commission), buy 10 more @ 120 (+3 commission):
    # avg cost = (10*100 + 3 + 10*120 + 3) / 20 = 110.3
    # sell all 20 @ 130, commission 3: gain = (130 - 110.3) * 20 - 3 = 391
    trades = _trades(
        {"date": "2026-01-10", "symbol": "SAP", "shares": 10, "price": 100.0, "commission": 3.0},
        {"date": "2026-02-10", "symbol": "SAP", "shares": 10, "price": 120.0, "commission": 3.0},
        {"date": "2026-06-10", "symbol": "SAP", "shares": -20, "price": 130.0, "commission": 3.0},
    )
    realized = _compute_realized_gains(trades)
    assert len(realized) == 1
    assert realized.iloc[0]["realized_gain_eur"] == pytest.approx(391.0)


def test_sparerpauschbetrag_zeroes_tax_under_allowance():
    trades = _trades(
        {"date": "2026-01-10", "symbol": "SAP", "shares": 10, "price": 100.0, "commission": 0.0},
        {"date": "2026-06-10", "symbol": "SAP", "shares": -10, "price": 105.0, "commission": 0.0},
    )
    result = estimate_after_tax_returns(trades, allowance_eur=1000.0)
    row = result.iloc[0]
    assert row["realized_gain_eur"] == pytest.approx(50.0)
    assert row["taxable_gain_eur"] == pytest.approx(0.0)
    assert row["estimated_tax_eur"] == pytest.approx(0.0)
    assert row["after_tax_gain_eur"] == pytest.approx(50.0)


def test_gain_above_allowance_is_taxed_on_the_excess_only():
    trades = _trades(
        {"date": "2026-01-10", "symbol": "SAP", "shares": 100, "price": 100.0, "commission": 0.0},
        {"date": "2026-06-10", "symbol": "SAP", "shares": -100, "price": 120.0, "commission": 0.0},
    )
    result = estimate_after_tax_returns(trades, tax_rate=0.26375, allowance_eur=1000.0)
    row = result.iloc[0]
    assert row["realized_gain_eur"] == pytest.approx(2000.0)
    assert row["taxable_gain_eur"] == pytest.approx(1000.0)  # 2000 - 1000 allowance
    assert row["estimated_tax_eur"] == pytest.approx(263.75)


def test_loss_year_carries_forward_to_offset_next_years_gain():
    trades = _trades(
        # 2026: loss of 500
        {"date": "2026-01-10", "symbol": "SAP", "shares": 10, "price": 100.0, "commission": 0.0},
        {"date": "2026-06-10", "symbol": "SAP", "shares": -10, "price": 50.0, "commission": 0.0},
        # 2027: gain of 2000
        {"date": "2027-01-10", "symbol": "SAP", "shares": 100, "price": 100.0, "commission": 0.0},
        {"date": "2027-06-10", "symbol": "SAP", "shares": -100, "price": 120.0, "commission": 0.0},
    )
    result = estimate_after_tax_returns(trades, allowance_eur=1000.0).set_index("year")

    loss_year = result.loc[2026]
    assert loss_year["realized_gain_eur"] == pytest.approx(-500.0)
    assert loss_year["estimated_tax_eur"] == pytest.approx(0.0)

    gain_year = result.loc[2027]
    assert gain_year["loss_carryforward_in_eur"] == pytest.approx(-500.0)
    # 2000 gain - 500 carried loss = 1500 net, - 1000 allowance = 500 taxable
    assert gain_year["taxable_gain_eur"] == pytest.approx(500.0)
    assert gain_year["estimated_tax_eur"] == pytest.approx(500.0 * 0.26375)


def test_empty_trades_returns_empty_frame():
    result = estimate_after_tax_returns(_trades())
    assert result.empty
