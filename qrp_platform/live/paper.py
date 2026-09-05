"""Paper broker: simulate a long-only equity account against live signals."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from qrp_platform.config import settings
from qrp_platform.data.loader import DataLoader
from qrp_platform.strategies.base import Strategy


class PaperBroker:
    """A minimal simulated broker.

    State:
        - cash: float
        - positions: dict[ticker, shares]
        - history: list[dict] — one entry per rebalance

    `run_one_tick(strategy, tickers)` fetches the latest data, runs the
    strategy, and rebalances toward the new weights. Safe to call repeatedly.
    """

    def __init__(
        self,
        capital: float | None = None,
        results_dir: Path | None = None,
        commission: float = 0.0005,
    ) -> None:
        self.initial_capital = float(capital if capital is not None else settings.paper_capital)
        self.cash = self.initial_capital
        self.positions: dict[str, float] = {}
        self.history: list[dict] = []
        self.commission = commission
        self.results_dir = Path(results_dir or settings.results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def equity(self, prices: dict[str, float] | None = None) -> float:
        """Mark-to-market equity given current prices (or last known)."""
        mtm = self.cash
        for ticker, shares in self.positions.items():
            if prices and ticker in prices:
                mtm += shares * prices[ticker]
            else:
                # assume last recorded price; if none, treat as 0
                last = next(
                    (h["prices"].get(ticker) for h in reversed(self.history) if "prices" in h),
                    0.0,
                )
                mtm += shares * (last or 0.0)
        return mtm

    def positions(self) -> dict[str, float]:
        return dict(self.positions)

    # ------------------------------------------------------------------
    def run_one_tick(
        self,
        strategy: Strategy,
        tickers: Iterable[str],
        lookback_days: int = 400,
        as_of: str | None = None,
    ) -> dict:
        """One rebalance cycle.

        1. Pull last `lookback_days` of close prices for each ticker.
        2. Run `strategy.generate_signals` on each.
        3. Convert latest weights to target dollar amounts.
        4. Trade deltas (with commission).
        """
        tickers = [t.strip().upper() for t in tickers if t.strip()]
        if not tickers:
            return {"ticker": [], "trades": [], "equity": self.equity()}

        end = as_of or datetime.utcnow().strftime("%Y-%m-%d")
        # The loader needs a `start` so we'll compute one from lookback_days.
        start = (
            pd.Timestamp(end) - pd.Timedelta(days=int(lookback_days * 1.5))
        ).strftime("%Y-%m-%d")

        loader = DataLoader()
        data = loader.load(tickers, start=start, end=end, refresh=False)

        if not data:
            return {"ticker": tickers, "trades": [], "equity": self.equity()}

        # Latest close prices
        prices = {t: float(df["close"].iloc[-1]) for t, df in data.items() if len(df) > 0}

        # Per-ticker latest weights
        latest_weights: dict[str, float] = {}
        for t, df in data.items():
            sigs = strategy.generate_signals(df)
            if "weight" in sigs and len(sigs) > 0:
                latest_weights[t] = float(sigs["weight"].iloc[-1])

        # Normalise (sum of abs = 1 if any nonzero)
        abs_sum = sum(abs(v) for v in latest_weights.values())
        if abs_sum > 0:
            latest_weights = {t: v / abs_sum for t, v in latest_weights.items()}

        # Current equity → target dollar weights → target share counts
        port_value = self.equity(prices)
        target_shares: dict[str, float] = {}
        for t, w in latest_weights.items():
            if t in prices and prices[t] > 0:
                target_shares[t] = (port_value * w) / prices[t]

        # Trade deltas
        trades = []
        all_tickers = set(self.positions) | set(target_shares)
        for t in all_tickers:
            current = self.positions.get(t, 0.0)
            target = target_shares.get(t, 0.0)
            delta = target - current
            if abs(delta) < 1e-6:
                continue
            price = prices.get(t, 0.0)
            notional = delta * price
            cost = abs(notional) * self.commission
            self.cash -= notional + cost
            self.positions[t] = target
            trades.append(
                {
                    "ticker": t,
                    "shares": round(delta, 4),
                    "price": round(price, 4),
                    "notional": round(notional, 2),
                    "commission": round(cost, 4),
                }
            )

        # Drop near-zero positions
        self.positions = {t: s for t, s in self.positions.items() if abs(s) > 1e-6}

        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "tickers": tickers,
            "weights": {t: round(w, 4) for t, w in latest_weights.items()},
            "prices": {t: round(p, 4) for t, p in prices.items()},
            "trades": trades,
            "equity": round(self.equity(prices), 2),
            "cash": round(self.cash, 2),
        }
        self.history.append(snapshot)
        self._append_log(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    def _log_path(self) -> Path:
        return self.results_dir / "paper_history.jsonl"

    def _append_log(self, snapshot: dict) -> None:
        with self._log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snapshot, default=str) + "\n")