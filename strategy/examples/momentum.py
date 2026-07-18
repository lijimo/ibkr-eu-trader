"""A minimal worked example of the SignalEngine contract: N-day momentum."""

from __future__ import annotations

import pandas as pd


class MomentumSignalEngine:
    """Long when trailing return over `lookback` days is positive, short when
    negative, scaled by how far the return is from zero (clipped to [-1, 1]).
    """

    def __init__(self, lookback: int = 20, scale: float = 10.0) -> None:
        self.lookback = lookback
        self.scale = scale

    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        signals: dict[str, pd.Series] = {}
        for symbol, df in data_map.items():
            trailing_return = df["close"].pct_change(self.lookback)
            signals[symbol] = (trailing_return * self.scale).clip(-1.0, 1.0).fillna(0.0)
        return signals
