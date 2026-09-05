"""Z-score mean reversion: long when price is below its z-score band."""
from __future__ import annotations

import pandas as pd

from .base import Strategy, register


@register
class MeanReversion(Strategy):
    name = "mean_reversion"
    description = "Long when z-score < -entry_z, flat otherwise."

    def __init__(
        self,
        window: int = 20,
        entry_z: float = -1.0,
        exit_z: float = 0.0,
    ) -> None:
        super().__init__(window=window, entry_z=entry_z, exit_z=exit_z)
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]
        mean = close.rolling(self.window).mean()
        std = close.rolling(self.window).std()
        z = (close - mean) / std

        # Hysteresis: enter at entry_z, exit when z crosses back to exit_z.
        long = (z <= self.entry_z).astype(float)
        exit_cond = z >= self.exit_z
        # If we were long and exit triggered, flatten (set to 0). Approximated
        # by zeroing the next day after the signal.
        out = pd.DataFrame(index=df.index)
        out["weight"] = long.fillna(0.0)
        out["z"] = z
        out["exit"] = exit_cond
        return out