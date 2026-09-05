"""12-1 cross-sectional momentum: long top-N by 12-month return ex last month."""
from __future__ import annotations

import pandas as pd

from .base import Strategy, register


@register
class Momentum(Strategy):
    name = "momentum"
    description = "Long top-N by 12-1 month return."

    def __init__(self, lookback: int = 252, skip: int = 21, top_n: int = 3) -> None:
        super().__init__(lookback=lookback, skip=skip, top_n=top_n)
        self.lookback = lookback
        self.skip = skip
        self.top_n = top_n

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # `df` here is a single ticker's OHLCV. For cross-sectional we
        # need a multi-ticker view. The engine handles cross-sectional
        # weighting via the panel; this per-ticker method just returns
        # a long/flat signal using its own momentum.
        close = df["close"]
        ret = close.pct_change(self.lookback).shift(-self.skip)  # forward skip = use month t-12..t-1
        # Actually momentum = past 12 months excluding last month:
        past_ret = close.shift(self.skip).pct_change(self.lookback)
        # Convert to long when positive, else 0 (binary).
        signal = (past_ret > 0).astype(float)

        out = pd.DataFrame(index=df.index)
        out["weight"] = signal.fillna(0.0)
        out["score"] = past_ret.fillna(0.0)  # for cross-sectional ranking
        return out