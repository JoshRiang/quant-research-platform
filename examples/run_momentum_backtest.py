"""Run a momentum backtest end-to-end.

Usage:
    python examples/run_momentum_backtest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python examples/run_momentum_backtest.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qrp_platform.backtest.engine import BacktestEngine
from qrp_platform.data.loader import DataLoader
from qrp_platform.strategies import get_strategy


def main() -> None:
    tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    start = "2020-01-01"
    end = "2024-01-01"

    loader = DataLoader()
    print(f"[example] loading {tickers} from {start} → {end}")
    data = loader.load(tickers, start=start, end=end)
    print(f"[example] loaded {len(data)} tickers")

    strat = get_strategy("momentum")
    print(f"[example] running strategy: {strat.name}")

    engine = BacktestEngine(initial_capital=100_000.0, walk_forward=False)
    result = engine.run(strat, data, start=start, end=end)

    print("\n=== METRICS ===")
    print(json.dumps(result.metrics, indent=2, default=str))

    run_dir = engine.save(result)
    print(f"\n[example] report saved → {run_dir}")
    print(f"           open: {run_dir / 'report.html'}")


if __name__ == "__main__":
    main()