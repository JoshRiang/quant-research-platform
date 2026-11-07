# Quant Research Platform

Vectorised backtest engine, strategy registry, FastAPI, Streamlit dashboard, paper broker.

`BacktestEngine` takes a `Strategy` instance and a dict of `{ticker: OHLCV DataFrame}`. It builds a close-price panel, runs each strategy to get target weights, lags them one day (no look-ahead), compounds portfolio returns with transaction costs proportional to turnover, and emits metrics (total return, CAGR, Sharpe, Sortino, max drawdown, Calmar, volatility, hit rate, turnover). Optional walk-forward mode splits the panel into in-sample / out-of-sample at 70/30 and reports both. Strategies register via the `@register` class decorator — built-ins: `momentum` (12-1 return), `mean_reversion` (z-score band entry/exit), `multi_factor` (trend + momentum composite). Results persist to `metrics.json` + an interactive HTML report (Plotly equity curve, drawdown, rolling Sharpe, metrics table).

```bash
git clone https://github.com/JoshRiang/quant-research-platform.git
cd quant-research-platform
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
# Smoke tests (synthetic data, no network)
pytest -v

# Start the FastAPI API
uvicorn qrp_platform.api.main:app --reload

# Start the Streamlit dashboard
streamlit run qrp_platform/dashboard/app.py
```

```python
from qrp_platform.backtest.engine import BacktestEngine
from qrp_platform.strategies import get_strategy, list_strategies
import pandas as pd, numpy as np

print(list_strategies())
# [{'name': 'momentum', ...}, {'name': 'mean_reversion', ...}, {'name': 'multi_factor', ...}]

# Synthetic OHLCV for 3 tickers
rng = np.random.default_rng(42)
dates = pd.bdate_range(end=pd.Timestamp('2024-01-01'), periods=300)
data = {}
for i, t in enumerate(['AAA', 'BBB', 'CCC']):
    ret = rng.normal(0.0003 + i*0.0001, 0.015 + i*0.002, size=300)
    price = 100 * np.exp(np.cumsum(ret))
    data[t] = pd.DataFrame({
        'open': price * (1 + rng.normal(0, 0.001, 300)),
        'high': price * (1 + np.abs(rng.normal(0, 0.003, 300))),
        'low': price * (1 - np.abs(rng.normal(0, 0.003, 300))),
        'close': price,
        'volume': rng.integers(100_000, 5_000_000, 300),
    }, index=dates)

strat = get_strategy('momentum')
engine = BacktestEngine(initial_capital=50_000.0)
result = engine.run(strat, data)

print(f'Total return: {result.metrics["total_return"]:.2%}')
print(f'Sharpe:       {result.metrics["sharpe"]:.3f}')
print(f'Max drawdown: {result.metrics["max_drawdown"]:.2%}')
run_dir = engine.save(result)
print(f'Report saved: {run_dir / "report.html"}')
```

Project structure:

```
quant-research-platform/
├── qrp_platform/
│   ├── __init__.py         # version 0.1.0
│   ├── config.py           # pydantic Settings: paper_capital, paper_cron, data_dir, results_dir, api_host/port
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py       # BacktestEngine (vectorised, walk-forward), BacktestResult, save()
│   │   ├── metrics.py      # compute_metrics: total_return, cagr, sharpe, sortino, mdd, calmar, vol, hit_rate, turnover
│   │   └── reports.py      # save_report: HTML with Plotly equity / drawdown / rolling-Sharpe
│   ├── strategies/
│   │   ├── __init__.py     # get_strategy, list_strategies, Strategy ABC + @register
│   │   ├── base.py         # Strategy ABC + registry
│   │   ├── momentum.py     # Momentum: long top-N by 12-1 return
│   │   ├── mean_reversion.py # MeanReversion: z-score band entry/exit
│   │   └── multi_factor.py # MultiFactor: trend + momentum composite
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py         # FastAPI: /health, /strategies, /backtest POST
│   ├── live/
│   │   ├── __init__.py
│   │   ├── paper.py        # PaperBroker: simulated account, run_one_tick rebalance, JSONL history
│   │   └── scheduler.py    # APScheduler cron wrapper for paper rebalancing
│   └── dashboard/
│       └── app.py          # Streamlit: Backtest Runner, Run History, Strategy Catalog
├── tests/test_smoke.py     # end-to-end: backtest on synthetic data, API, paper broker, registry, metrics
├── examples/run_momentum_backtest.py
├── docker-compose.yml
├── pytest.ini
├── requirements.txt        # pandas, numpy, fastapi, uvicorn, streamlit, plotly, scikit-learn, yfinance, APScheduler
├── LICENSE
└── README.md
```

Testing:

```bash
pytest -v
```

Smoke tests use synthetic data — no network required.

License: MIT — see [LICENSE](LICENSE).

Author: Joshua Riangkamang — [github.com/JoshRiang](https://github.com/JoshRiang)
