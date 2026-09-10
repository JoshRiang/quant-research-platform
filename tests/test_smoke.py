"""Smoke tests for the quant research qrp_platform.

These run WITHOUT network access — they use synthetic price data so the
test suite is fast and offline-friendly.
"""

# Maintenance: last reviewed 2026-09-10 (daily improvement cycle)
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_synthetic_data(
    tickers: list[str],
    n_days: int = 300,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """Generate deterministic synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp("2024-01-01"), periods=n_days)
    out: dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers):
        # Different drift/vol per ticker
        drift = 0.0003 + i * 0.0001
        vol = 0.015 + i * 0.002
        ret = rng.normal(drift, vol, size=n_days)
        price = 100 * np.exp(np.cumsum(ret))
        df = pd.DataFrame(
            {
                "open": price * (1 + rng.normal(0, 0.001, size=n_days)),
                "high": price * (1 + np.abs(rng.normal(0, 0.003, size=n_days))),
                "low": price * (1 - np.abs(rng.normal(0, 0.003, size=n_days))),
                "close": price,
                "volume": rng.integers(100_000, 5_000_000, size=n_days),
            },
            index=dates,
        )
        out[t] = df
    return out


@pytest.fixture
def synthetic_data() -> dict[str, pd.DataFrame]:
    return _make_synthetic_data(["AAA", "BBB", "CCC"], n_days=300, seed=7)


# ---------------------------------------------------------------------------
# 1. Backtest end-to-end
# ---------------------------------------------------------------------------
def test_backtest_runs_and_produces_metrics(synthetic_data, tmp_path):
    from qrp_platform.backtest.engine import BacktestEngine
    from qrp_platform.strategies import get_strategy

    strat = get_strategy("momentum")
    engine = BacktestEngine(initial_capital=50_000.0)
    result = engine.run(strat, synthetic_data)

    # Equity curve exists
    assert len(result.equity) > 0
    assert result.equity.iloc[0] == 50_000.0
    # Metrics populated
    for key in ("total_return", "sharpe", "max_drawdown", "volatility", "hit_rate", "equity_final"):
        assert key in result.metrics, f"missing metric: {key}"
    # Weights panel
    assert result.weights.shape[1] == len(synthetic_data)
    # Save report to tmp
    run_dir = engine.save(result, out_dir=tmp_path)
    assert (run_dir / "metrics.json").exists()
    assert (run_dir / "report.html").exists()

    # metrics.json is valid JSON
    parsed = json.loads((run_dir / "metrics.json").read_text())
    assert "metrics" in parsed
    assert parsed["strategy"] == "momentum"


# ---------------------------------------------------------------------------
# 2. FastAPI /health
# ---------------------------------------------------------------------------
def test_api_health():
    from fastapi.testclient import TestClient
    from qrp_platform.api.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "strategies" in body
    assert body["strategies"] >= 3


def test_api_strategies_endpoint():
    from fastapi.testclient import TestClient
    from qrp_platform.api.main import app

    client = TestClient(app)
    r = client.get("/strategies")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert {"momentum", "mean_reversion", "multi_factor"} <= names


# ---------------------------------------------------------------------------
# 3. Paper broker single tick
# ---------------------------------------------------------------------------
def test_paper_broker_single_tick(monkeypatch, tmp_path, synthetic_data):
    """Run a single rebalance against synthetic data without network."""
    from qrp_platform.live.paper import PaperBroker
    from qrp_platform.strategies import get_strategy

    # Bypass the network: monkeypatch DataLoader.load to return our synthetic data.
    from qrp_platform.data import loader as loader_mod

    class _StubLoader:
        def __init__(self, *args, **kwargs):
            pass

        def load(self, tickers, start, end, refresh=False):  # noqa: ARG002
            return {t: synthetic_data[t] for t in tickers if t in synthetic_data}

    monkeypatch.setattr(loader_mod, "DataLoader", _StubLoader)

    strat = get_strategy("momentum")
    broker = PaperBroker(capital=100_000.0, results_dir=tmp_path)
    snap = broker.run_one_tick(strat, ["AAA", "BBB"])

    assert "trades" in snap
    assert "equity" in snap
    assert snap["equity"] > 0
    assert len(broker.history) == 1
    assert (tmp_path / "paper_history.jsonl").exists()


# ---------------------------------------------------------------------------
# 4. Strategy registry completeness
# ---------------------------------------------------------------------------
def test_strategy_registry_has_three():
    from qrp_platform.strategies import list_strategies

    names = {s["name"] for s in list_strategies()}
    assert {"momentum", "mean_reversion", "multi_factor"} <= names


# ---------------------------------------------------------------------------
# 5. Metrics sanity
# ---------------------------------------------------------------------------
def test_metrics_on_constant_equity():
    """A flat equity curve should give zero return, zero sharpe, zero max DD."""
    from qrp_platform.backtest.metrics import compute_metrics

    eq = pd.Series([100.0] * 100, index=pd.bdate_range("2020-01-01", periods=100))
    m = compute_metrics(eq)
    assert m["total_return"] == 0.0
    assert m["sharpe"] == 0.0
    assert m["max_drawdown"] == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))