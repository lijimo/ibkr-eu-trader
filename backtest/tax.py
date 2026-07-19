"""A post-hoc estimate of German capital gains tax on a backtest's realized
trades. Deliberately kept separate from the equity curve in ``engine.py``:
unlike commissions, tax isn't a deterministic per-trade cost — it's computed
on *net annual realized* gains after loss offsetting, depends on an
allowance, and (for IBKR specifically) is never withheld at the source the
way a German bank would, so it doesn't belong inside a per-trade cost model.

This is an ESTIMATE, not tax advice:
- Cost basis is tracked with the moving-average method (``gleitender
  Durchschnittspreis``), the convention German Depot tax accounting uses —
  not FIFO. IBKR's own tax certificate may compute slightly different
  figures; use this to compare strategies, not to file a return.
- Excludes Kirchensteuer (church tax) by default — pass a higher
  ``tax_rate`` to include it (add 8-9% of the 25% base rate on top of
  ``GERMAN_CAPITAL_GAINS_TAX_RATE``).
- Excludes dividend income entirely — this engine doesn't model dividends.
- Unrealized gains on positions still open at the end of the backtest are
  correctly left untaxed (German tax only taxes gains on sale).
- You are personally responsible for declaring gains from IBKR yourself via
  Anlage KAP — IBKR does not withhold this tax at source.
"""

from __future__ import annotations

import pandas as pd

GERMAN_CAPITAL_GAINS_TAX_RATE = 0.26375  # 25% Abgeltungsteuer + 5.5% Soli on that tax
DEFAULT_SPARERPAUSCHBETRAG_EUR = 1000.0  # single-filer annual allowance, 2026


def _compute_realized_gains(trades: pd.DataFrame) -> pd.DataFrame:
    """One row per closing (sell) trade: {date, symbol, realized_gain_eur}.

    Tracks a moving-average cost basis per symbol. A buy rolls its
    commission into the average cost; a sell realizes
    ``(price - avg_cost) * |shares| - commission`` and leaves the average
    cost of the remaining position unchanged.
    """
    if trades.empty:
        return pd.DataFrame(columns=["date", "symbol", "realized_gain_eur"])

    rows: list[dict] = []
    avg_cost: dict[str, float] = {}
    held: dict[str, float] = {}

    for _, trade in trades.sort_values(["symbol", "date"]).iterrows():
        symbol = trade["symbol"]
        delta = trade["shares"]
        price = trade["price"]
        commission = trade["commission"]
        prior_shares = held.get(symbol, 0.0)
        prior_cost = avg_cost.get(symbol, 0.0)

        if delta > 0:
            new_shares = prior_shares + delta
            total_cost = prior_shares * prior_cost + delta * price + commission
            avg_cost[symbol] = total_cost / new_shares if new_shares else 0.0
            held[symbol] = new_shares
        elif delta < 0:
            closed = min(-delta, prior_shares)
            realized_gain = (price - prior_cost) * closed - commission
            rows.append({"date": trade["date"], "symbol": symbol, "realized_gain_eur": realized_gain})
            held[symbol] = prior_shares - closed
            # avg_cost of the remaining position is unchanged by a sell

    return pd.DataFrame(rows, columns=["date", "symbol", "realized_gain_eur"])


def estimate_after_tax_returns(
    trades: pd.DataFrame,
    *,
    tax_rate: float = GERMAN_CAPITAL_GAINS_TAX_RATE,
    allowance_eur: float = DEFAULT_SPARERPAUSCHBETRAG_EUR,
) -> pd.DataFrame:
    """One row per calendar year with realized/taxable gains and estimated tax.

    Applies annual netting with loss carryforward (a loss year's shortfall
    reduces the following year's taxable gain before the allowance is
    applied) and the Sparerpauschbetrag allowance.
    """
    realized = _compute_realized_gains(trades)
    if realized.empty:
        return pd.DataFrame(
            columns=[
                "year",
                "realized_gain_eur",
                "loss_carryforward_in_eur",
                "allowance_used_eur",
                "taxable_gain_eur",
                "estimated_tax_eur",
                "after_tax_gain_eur",
            ]
        )

    realized = realized.copy()
    realized["year"] = pd.to_datetime(realized["date"]).dt.year
    by_year = realized.groupby("year")["realized_gain_eur"].sum().sort_index()

    rows: list[dict] = []
    loss_carryforward = 0.0
    for year, gross_gain in by_year.items():
        carryforward_in = loss_carryforward
        net_after_carryforward = gross_gain + carryforward_in

        if net_after_carryforward <= 0:
            loss_carryforward = net_after_carryforward
            allowance_used = 0.0
            taxable_gain = 0.0
            tax = 0.0
        else:
            loss_carryforward = 0.0
            allowance_used = min(allowance_eur, net_after_carryforward)
            taxable_gain = net_after_carryforward - allowance_used
            tax = taxable_gain * tax_rate

        rows.append(
            {
                "year": int(year),
                "realized_gain_eur": float(gross_gain),
                "loss_carryforward_in_eur": float(carryforward_in),
                "allowance_used_eur": float(allowance_used),
                "taxable_gain_eur": float(taxable_gain),
                "estimated_tax_eur": float(tax),
                "after_tax_gain_eur": float(gross_gain - tax),
            }
        )

    return pd.DataFrame(rows)
