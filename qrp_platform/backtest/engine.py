"""Walk-forward vectorised backtest engine."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from qrp_platform.config import settings
from qrp_platform.strategies.base import Strategy

from .metrics import compute_metrics


@dataclass
class BacktestResult:
    """Container for backtest outputs."""

    run_id: str
    strategy_name: str
    tickers: list[str]
    metrics: dict[str, float]
    equity: pd.Series
    weights: pd.DataFrame
    returns: pd.Series
    start: str
    end: str
    initial_capital: float

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "strategy": self.strategy_name,
            "tickers": self.tickers,
            "start": self.start,
            "end": self.end,
            "initial_capital": self.initial_capital,
            "metrics": self.metrics,
        }


class BacktestEngine:
    """Long-only / long-short vectorised backtester with optional walk-forward.

    Inputs:
        - `strategy`: instance of `Strategy`
        - `data`: dict of {ticker: OHLCV DataFrame}, all aligned to a common
          date index (the engine auto-aligns them).

    Approach:
        1. Build a close-price panel `close[ticker, date]`.
        2. For each ticker call `strategy.generate_signals(df)` and read the
           `weight` column.
        3. Stack into a `weights[ticker, date]` panel.
        4. Convert to daily portfolio returns:  r_p[t] = sum_i w_i[t-1] * r_i[t]
        5. Compound into equity.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission: float = 0.0005,  # 5 bps per unit turnover
        walk_forward: bool = False,
        train_pct: float = 0.7,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission = commission
        self.walk_forward = walk_forward
        self.train_pct = train_pct

    # ------------------------------------------------------------------
    def _build_panel(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Align tickers to a common date index and return close-price panel."""
        series = []
        for ticker, df in data.items():
            s = df["close"].copy()
            s.name = ticker
            series.append(s)
        panel = pd.concat(series, axis=1).sort_index().ffill()
        return panel

    def _build_returns(self, close: pd.DataFrame) -> pd.DataFrame:
        return close.pct_change().fillna(0.0)

    # ------------------------------------------------------------------
    def run(
        self,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
        start: str | None = None,
        end: str | None = None,
    ) -> BacktestResult:
        if not data:
            raise ValueError("No data passed to backtest.")

        tickers = list(data.keys())
        close = self._build_panel(data)
        rets = self._build_returns(close)

        if start:
            close = close.loc[close.index >= pd.Timestamp(start)]
            rets = rets.loc[rets.index >= pd.Timestamp(start)]
        if end:
            close = close.loc[close.index <= pd.Timestamp(end)]
            rets = rets.loc[rets.index <= pd.Timestamp(end)]

        # Per-ticker signals
        weight_frames = {}
        for ticker, df in data.items():
            sigs = strategy.generate_signals(df)
            sigs = sigs.reindex(close.index).fillna(0.0)
            weight_frames[ticker] = sigs["weight"].clip(-1.0, 1.0)

        weights = pd.concat(weight_frames, axis=1).fillna(0.0)
        weights.columns = tickers
        # Normalise to sum-of-abs(weights) = 1 if any nonzero
        abs_sum = weights.abs().sum(axis=1)
        weights = weights.div(abs_sum.where(abs_sum > 0, 1.0), axis=0)

        # Lag weights one day (no look-ahead)
        lagged = weights.shift(1).fillna(0.0)

        # Portfolio returns
        port_ret = (lagged * rets).sum(axis=1)

        # Apply transaction costs proportional to turnover
        turnover = weights.diff().abs().sum(axis=1).fillna(0.0)
        port_ret_after = port_ret - turnover * self.commission

        equity = (1.0 + port_ret_after).cumprod() * self.initial_capital
        equity.iloc[0] = self.initial_capital

        metrics = compute_metrics(equity, turnover=turnover)

        if self.walk_forward:
            metrics = self._walk_forward_validate(strategy, data, metrics)

        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        return BacktestResult(
            run_id=run_id,
            strategy_name=strategy.name or strategy.__class__.__name__,
            tickers=tickers,
            metrics=metrics,
            equity=equity,
            weights=weights,
            returns=port_ret_after,
            start=str(close.index[0].date()),
            end=str(close.index[-1].date()),
            initial_capital=self.initial_capital,
        )

    # ------------------------------------------------------------------
    def _walk_forward_validate(
        self,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
        base_metrics: dict[str, float],
    ) -> dict[str, float]:
        """Re-run on the OUT-OF-SAMPLE tail (last `1 - train_pct` of dates)
        and return those metrics. Original metrics retained in result via
        concatenation."""
        # Determine split from the equity index (last close-date)
        # Using the close panel rebuilt for consistency
        panel = self._build_panel(data)
        n = len(panel)
        split = int(n * self.train_pct)
        oos_start = panel.index[split]

        oos_data = {t: df.loc[df.index >= oos_start] for t, df in data.items()}
        oos_engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission=self.commission,
            walk_forward=False,
        )
        oos_result = oos_engine.run(strategy, oos_data)
        oos_metrics = {f"oos_{k}": v for k, v in oos_result.metrics.items()}
        merged = {**base_metrics, **oos_metrics}
        return merged

    # ------------------------------------------------------------------
    def save(
        self,
        result: BacktestResult,
        out_dir: Path | None = None,
    ) -> Path:
        """Persist metrics + report; return run directory."""
        from .reports import save_report

        out_dir = Path(out_dir or settings.results_dir) / result.run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        metrics_path = out_dir / "metrics.json"
        metrics_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))

        report_path = save_report(result, out_dir)
        result.metrics.setdefault("report_path", str(report_path))
        # rewrite with report path included
        metrics_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
        return out_dir