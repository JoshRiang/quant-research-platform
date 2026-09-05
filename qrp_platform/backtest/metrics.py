"""Performance metrics for an equity-curve series."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_metrics(
    equity: pd.Series,
    turnover: pd.Series | None = None,
    risk_free: float = 0.0,
) -> dict[str, float]:
    """Compute a standard quant metrics suite from an equity curve.

    `equity` is a time-indexed portfolio value series (starts > 0).
    """
    if equity.empty:
        raise ValueError("Empty equity curve")

    equity = equity.astype(float)
    rets = equity.pct_change().dropna()

    if rets.empty:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "volatility": 0.0,
            "hit_rate": 0.0,
            "turnover": float(turnover.mean()) if turnover is not None else 0.0,
            "equity_final": float(equity.iloc[-1]),
        }

    # Periods per year (assume daily)
    periods = 252

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)

    days = (equity.index[-1] - equity.index[0]).days
    years = days / 365.25 if days > 0 else 1.0
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    vol = rets.std() * math.sqrt(periods)
    mean = rets.mean() * periods - risk_free
    sharpe = mean / vol if vol > 0 else 0.0

    downside = rets[rets < 0].std() * math.sqrt(periods)
    sortino = mean / downside if downside > 0 else 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = float(drawdown.min())

    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    hit_rate = float((rets > 0).sum() / len(rets))

    avg_turnover = float(turnover.mean()) if turnover is not None and not turnover.empty else 0.0

    return {
        "total_return": total_return,
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": max_dd,
        "calmar": float(calmar),
        "volatility": float(vol),
        "hit_rate": hit_rate,
        "turnover": avg_turnover,
        "equity_final": float(equity.iloc[-1]),
    }