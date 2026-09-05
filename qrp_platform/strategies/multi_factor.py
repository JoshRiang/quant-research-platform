"""Multi-factor composite: weighted blend of momentum, mean-reversion and trend filters.

Each per-ticker signal here is a blend. The engine applies cross-sectional
weighting (equal-weight top quartile) on top.
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy, register


@register
class MultiFactor(Strategy):
    name = "multi_factor"
    description = "Composite momentum + trend filter (long-only)."

    def __init__(
        self,
        fast: int = 20,
        slow: int = 100,
        mom: int = 126,
    ) -> None:
        super().__init__(fast=fast, slow=slow, mom=mom)
        self.fast = fast
        self.slow = slow
        self.mom = mom

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]
        sma_fast = close.rolling(self.fast).mean()
        sma_slow = close.rolling(self.slow).mean()

        # Trend: fast above slow
        trend = (sma_fast > sma_slow).astype(float)

        # Momentum: positive 6-month return
        mom_ret = close.pct_change(self.mom)
        mom_signal = (mom_ret > 0).astype(float)

        # Composite (both must agree)
        weight = trend * mom_signal

        out = pd.DataFrame(index=df.index)
        out["weight"] = weight.fillna(0.0)
        out["score"] = mom_ret.fillna(0.0)
        return out