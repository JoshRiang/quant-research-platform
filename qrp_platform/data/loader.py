"""Price data loading.

The platform needs OHLCV frames keyed by ticker, and it needs that to be
cheap on the second call: a backtest re-run should not re-download two years
of history. Three layers do that here.

  * `normalise` forces the column names to the lower-case OHLCV the rest of
    the platform expects (the engine reads `df["close"]`), accepts whatever
    the vendor returns, and sorts the index.
  * `ParquetCache` stores one file per ticker under `settings.data_dir` and
    reports the last stored date so a load can ask for the delta only.
  * `DataLoader` wires the two together, with `refresh=False` meaning
    "extend from the cache" and `refresh=True` meaning "re-download".

Network access goes through yfinance. If it is not installed, or the call
returns nothing, the loader raises a DataError rather than silently handing
back an empty dict, because a silent empty result looks exactly like a
successful load of a delisted ticker.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from qrp_platform.config import settings

OHLCV = ["open", "high", "low", "close", "volume"]


class DataError(RuntimeError):
    """Raised when price data cannot be produced."""


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Force lower-case OHLCV columns, sort by date, drop junk rows.

    Vendors return `Open`/`OPEN`/`close` inconsistently, and a multi-index
    column frame comes back when more than one ticker is requested. Normalising
    at the boundary is what lets the engine assume one shape.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [str(c[0]) for c in df.columns]

    renamed = {str(c).strip().lower(): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for col in OHLCV:
        src = renamed.get(col)
        if src is not None:
            out[col] = pd.to_numeric(df[src], errors="coerce")

    if "close" not in out.columns or out["close"].isna().all():
        raise DataError("frame has no usable 'close' column")

    # Reconstruct any missing field from close rather than dropping the row.
    for col in OHLCV:
        if col not in out.columns:
            out[col] = out["close"] if col != "volume" else 0.0

    out = out[OHLCV].sort_index()
    out = out[~out["close"].isna()]
    out.index = pd.DatetimeIndex(out.index).normalize()
    return out


@dataclass
class ParquetCache:
    """One Parquet file per ticker under `root`."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, ticker: str) -> Path:
        return self.root / f"{ticker.upper()}.parquet"

    def read(self, ticker: str) -> Optional[pd.DataFrame]:
        p = self.path(ticker)
        if not p.exists():
            return None
        try:
            return pd.read_parquet(p)
        except Exception:
            return None

    def write(self, ticker: str, df: pd.DataFrame) -> None:
        df.to_parquet(self.path(ticker), compression="snappy")

    def last_date(self, ticker: str) -> Optional[pd.Timestamp]:
        df = self.read(ticker)
        if df is None or df.empty:
            return None
        return pd.Timestamp(df.index.max())


class DataLoader:
    """Loads OHLCV frames, caching to Parquet."""

    def __init__(self, data_dir: Optional[Path] = None, cache: Optional[ParquetCache] = None):
        root = Path(data_dir) if data_dir is not None else Path(settings.data_dir) / "bars"
        self.cache = cache or ParquetCache(root)

    # ---- public API ----------------------------------------------------
    def load(
        self,
        tickers: Iterable[str],
        start: str,
        end: str,
        refresh: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        """Return {ticker: OHLCV frame} covering [start, end].

        `refresh=False` extends an existing cache file with only the rows it
        is missing; `refresh=True` re-downloads the full window.
        """
        tickers = [t.upper() for t in tickers]
        out: Dict[str, pd.DataFrame] = {}

        for ticker in tickers:
            cached = None if refresh else self.cache.read(ticker)

            if cached is not None and not cached.empty:
                have_end = pd.Timestamp(cached.index.max())
                want_end = pd.Timestamp(end)
                if have_end >= want_end:
                    out[ticker] = self._slice(cached, start, end)
                    continue
                fetch_start = (have_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                fetch_start = start

            fresh = self._download(ticker, fetch_start, end)
            if fresh is None or fresh.empty:
                if cached is not None and not cached.empty:
                    out[ticker] = self._slice(cached, start, end)
                    continue
                raise DataError(f"no data returned for {ticker} between {fetch_start} and {end}")

            merged = fresh if cached is None else pd.concat([cached, fresh])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            self.cache.write(ticker, merged)
            out[ticker] = self._slice(merged, start, end)

        return out

    # ---- internals -----------------------------------------------------
    @staticmethod
    def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        return df.loc[(df.index >= lo) & (df.index <= hi)]

    @staticmethod
    def _download(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - depends on env
            raise DataError("yfinance is not installed") from exc

        try:
            raw = yf.download(
                ticker,
                start=start,
                end=end,
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        except Exception as exc:
            raise DataError(f"download failed for {ticker}: {exc}") from exc

        if raw is None or raw.empty:
            return None
        return normalise(raw)
