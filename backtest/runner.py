"""``run_dir`` in, artifacts out. Each run is a self-contained, diffable
directory — no database, no schema migration.

    run_dir/
    ├── config.json        # what was requested
    ├── artifacts/
    │   ├── metrics.csv
    │   ├── equity.csv
    │   ├── trades.csv
    │   └── run_card.json  # hashed config+metrics receipt
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from backtest.engine import BacktestConfig, run_backtest
from backtest.run_card import write_run_card
from ibkr.market_data import get_historical_bars
from strategy.signal_engine import SignalEngine


def run_backtest_to_dir(
    run_dir: Path,
    *,
    engine: SignalEngine,
    symbols: list[str],
    duration: str = "1 Y",
    config: BacktestConfig | None = None,
) -> dict[str, Any]:
    cfg = config or BacktestConfig()
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    config_payload = {"symbols": symbols, "duration": duration, **asdict(cfg)}
    (run_dir / "config.json").write_text(json.dumps(config_payload, indent=2) + "\n", encoding="utf-8")

    data_map = {
        symbol: get_historical_bars(symbol, exchange=cfg.exchange, currency=cfg.currency, duration=duration)
        for symbol in symbols
    }
    data_map = {s: df for s, df in data_map.items() if not df.empty}
    if not data_map:
        raise ValueError("no historical data available for any requested symbol")

    result = run_backtest(engine, data_map, cfg)

    result.equity_curve.to_csv(artifacts_dir / "equity.csv", header=["equity_eur"], index_label="date")
    result.trades.to_csv(artifacts_dir / "trades.csv", index=False)
    metrics = {
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "turnover_eur": result.turnover_eur,
        "trade_count": len(result.trades),
    }
    pd.DataFrame([metrics]).to_csv(artifacts_dir / "metrics.csv", index=False)
    write_run_card(artifacts_dir, config=config_payload, metrics=metrics)

    return {"status": "ok", "run_dir": str(run_dir), "metrics": metrics}
