"""Backtest tool. v1 only supports strategies already registered in code
(strategy/examples/) — the agent picks one by name and parameterizes it,
rather than authoring new strategy code on the fly. Broadening this to
agent-authored strategies is a deliberate later step, not an MVP goal.
"""

from __future__ import annotations

from pathlib import Path

from anthropic import beta_tool

from backtest.engine import BacktestConfig
from backtest.runner import run_backtest_to_dir
from safety.paths import get_runtime_root
from strategy.examples.momentum import MomentumSignalEngine

_STRATEGY_REGISTRY = {
    "momentum": MomentumSignalEngine,
}


@beta_tool
def run_backtest(
    symbols: list[str],
    strategy: str = "momentum",
    duration: str = "1 Y",
    exchange: str = "IBIS",
    transaction_tax_pct: float | None = None,
) -> dict:
    """Backtest a registered strategy against EUR-denominated symbols.

    Args:
        symbols: Stock symbols to include, e.g. ["SAP", "SIE", "ALV"].
        strategy: Registered strategy name. Currently available: "momentum".
        duration: IBKR duration string, e.g. "1 Y", "6 M".
        exchange: IBKR exchange code. Default IBIS (Xetra). Also supported:
            FWB (Frankfurt), SWB (Stuttgart), SBF (Euronext Paris), AEB
            (Euronext Amsterdam), ENEXT.BE (Euronext Brussels), BVME
            (Borsa Italiana / Milan).
        transaction_tax_pct: Required for SBF and BVME — France and Italy
            levy a transaction tax on purchases of qualifying large-cap
            stocks (currently 0.4% and 0.2% respectively). Pass 0.0 if the
            requested symbol doesn't currently qualify; there is no safe
            default, so the call errors without it on those two exchanges.
    """
    if strategy not in _STRATEGY_REGISTRY:
        return {"status": "error", "error": f"unknown strategy {strategy!r}; available: {list(_STRATEGY_REGISTRY)}"}

    engine = _STRATEGY_REGISTRY[strategy]()
    run_dir = get_runtime_root() / "runs" / f"{strategy}_{'-'.join(symbols)}"
    try:
        config = BacktestConfig(exchange=exchange, transaction_tax_pct=transaction_tax_pct)
        return run_backtest_to_dir(run_dir, engine=engine, symbols=symbols, duration=duration, config=config)
    except Exception as exc:  # noqa: BLE001 - report to the agent, don't crash the tool loop
        return {"status": "error", "error": str(exc)}
