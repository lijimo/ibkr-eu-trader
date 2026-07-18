"""The strategy contract. Everything else in this app — the backtest engine,
the agent's ``run_backtest`` tool, and eventually live execution — targets
this one interface. Deliberately small: a strategy is a function from bars
to signals, nothing more.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class SignalEngine(Protocol):
    """A trading strategy.

    Implementations should be pure with respect to ``data_map`` — no network
    calls, no broker access, no hidden state beyond what's passed in. That's
    what makes a strategy backtestable and, later, safely runnable live
    without rewriting it.
    """

    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        """Compute a signal for each symbol.

        Args:
            data_map: symbol -> OHLCV DataFrame (columns: open, high, low,
                close, volume; DatetimeIndex). May carry extra columns
                (e.g. fundamentals) that a given strategy chooses to use.

        Returns:
            symbol -> signal Series, values in [-1.0, 1.0], index-aligned to
            the corresponding input DataFrame. Positive = long bias,
            negative = short bias, 0 = flat.
        """
        ...
