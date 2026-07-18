"""A single, EUR/Xetra-correct backtest engine.

Vibe-Trading's equivalent engine is named "global" but only actually
branches cost/lot-size assumptions for US vs. HK — anything else (including
Xetra) silently gets US-style zero-commission, fractional-share assumptions,
which understates costs and can make a strategy look profitable when it
wouldn't be. This engine has exactly one cost model (Xetra-style: fixed +
percentage commission, whole-share lots, EUR-denominated) and refuses to run
rather than silently defaulting when given a market it doesn't recognize.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from strategy.signal_engine import SignalEngine


class UnsupportedMarketError(RuntimeError):
    """Raised instead of silently applying the wrong cost model."""


# Approximate Xetra/German-broker-typical cost shape. NOT calibrated against
# a real broker fee schedule yet — replace with your actual IBKR commission
# tier before trusting backtest results. Deliberately conservative (a real
# schedule is very unlikely to be cheaper than this).
DEFAULT_COMMISSION_FIXED_EUR = 4.0
DEFAULT_COMMISSION_PCT = 0.001  # 10 bps
SUPPORTED_EXCHANGES = frozenset({"IBIS", "FWB", "SWB"})  # Xetra, Frankfurt, Stuttgart


@dataclass(frozen=True)
class BacktestConfig:
    exchange: str = "IBIS"
    currency: str = "EUR"
    initial_capital_eur: float = 100_000.0
    commission_fixed_eur: float = DEFAULT_COMMISSION_FIXED_EUR
    commission_pct: float = DEFAULT_COMMISSION_PCT

    def __post_init__(self) -> None:
        if self.exchange.strip().upper() not in SUPPORTED_EXCHANGES:
            raise UnsupportedMarketError(
                f"backtest engine does not have a cost model for exchange={self.exchange!r}; "
                f"supported: {sorted(SUPPORTED_EXCHANGES)}. Refusing to run with a "
                "wrong-market cost assumption rather than silently defaulting."
            )
        if self.currency.strip().upper() != "EUR":
            raise UnsupportedMarketError(
                f"backtest engine is EUR-only; got currency={self.currency!r}"
            )


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    total_return_pct: float
    max_drawdown_pct: float
    turnover_eur: float


def run_backtest(
    engine: SignalEngine,
    data_map: dict[str, pd.DataFrame],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a single-currency, whole-share, next-bar-execution backtest.

    Deliberately simple (no slippage model, no partial fills, no margin) —
    this is a starting point, not a production-grade simulator. Positions
    are sized as equal-weight across symbols with a nonzero signal on each
    bar; each rebalance charges the commission model above.
    """
    cfg = config or BacktestConfig()
    symbols = list(data_map.keys())
    signals = engine.generate(data_map)

    all_dates = sorted(set().union(*(df.index for df in data_map.values())))
    cash = cfg.initial_capital_eur
    shares: dict[str, float] = {s: 0.0 for s in symbols}
    equity_curve: dict[pd.Timestamp, float] = {}
    trade_rows: list[dict] = []
    turnover_eur = 0.0

    for dt in all_dates:
        active = [s for s in symbols if dt in signals.get(s, pd.Series(dtype=float)).index]
        target_weight = 1.0 / len(active) if active else 0.0

        portfolio_value = cash + sum(
            shares[s] * data_map[s].loc[dt, "close"] for s in symbols if dt in data_map[s].index
        )

        for s in active:
            price = data_map[s].loc[dt, "close"]
            sig = signals[s].loc[dt]
            target_value = portfolio_value * target_weight * sig
            target_shares = math.floor(abs(target_value) / price) * (1 if target_value >= 0 else -1)
            delta_shares = target_shares - shares[s]
            if delta_shares == 0:
                continue
            trade_notional = abs(delta_shares) * price
            commission = cfg.commission_fixed_eur + trade_notional * cfg.commission_pct
            cash -= delta_shares * price + commission
            shares[s] = target_shares
            turnover_eur += trade_notional
            trade_rows.append(
                {"date": dt, "symbol": s, "shares": delta_shares, "price": price, "commission": commission}
            )

        equity_curve[dt] = cash + sum(
            shares[s] * data_map[s].loc[dt, "close"] for s in symbols if dt in data_map[s].index
        )

    equity = pd.Series(equity_curve).sort_index()
    total_return_pct = (equity.iloc[-1] / cfg.initial_capital_eur - 1.0) * 100 if not equity.empty else 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown_pct = float(drawdown.min() * 100) if not equity.empty else 0.0

    return BacktestResult(
        equity_curve=equity,
        trades=pd.DataFrame(trade_rows),
        total_return_pct=float(total_return_pct),
        max_drawdown_pct=max_drawdown_pct,
        turnover_eur=turnover_eur,
    )
