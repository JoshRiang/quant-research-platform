# Quant Research Platform

> End-to-end quantitative research platform: data ingestion → strategy research → walk-forward backtesting → paper trading → interactive dashboard & API.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)](https://streamlit.io)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](Dockerfile)

The centerpiece of my portfolio. A complete, production-shaped quantitative research stack:

- **Plugin strategy architecture** — drop a `.py` file in `qrp_platform/strategies/` and it's auto-registered.
- **Walk-forward backtester** with full metrics suite (Sharpe, Sortino, max DD, Calmar, hit rate, turnover).
- **HTML reports** with interactive Plotly charts (equity curve, drawdown, rolling Sharpe, signals).
- **Paper trading loop** that simulates a brokerage against live data — no real money, real PnL.
- **FastAPI control plane** (`/strategies`, `/backtest`, `/health`) — schedule & run jobs from anywhere.
- **Streamlit dashboard** — equity curves, signal viewer, backtest launcher, live PnL monitor.
- **Multi-stage Docker** + `docker-compose.yml` (api + dashboard + scheduler).

---

## 🏛️ Architecture

```
                          ┌─────────────────────┐
                          │   Streamlit UI      │
                          │   :8501             │
                          └──────────┬──────────┘
                                     │ HTTP
┌────────────────────┐               │
│  yfinance / CSV    │      ┌────────▼─────────┐         ┌────────────────────┐
│  ──────────────►   │      │   FastAPI :8000  │  cron   │   Scheduler        │
│  DataLoader        │      │   /strategies    │◄────────│   (APScheduler)    │
│  (cached CSVs)     │      │   /backtest      │ trigger └────────────────────┘
└─────────┬──────────┘      │   /health        │                  │
          │                 └────────┬─────────┘                  ▼
          ▼                          │                    ┌───────────────┐
┌────────────────────┐                ▼                    │  Paper Loop   │
│ Parquet Store      │       ┌────────────────┐            │  (broker sim) │
│ (cold storage)     │◄──────│  Backtester    │            └───────┬───────┘
└────────────────────┘       │  engine.py     │                    │
                             └────────┬───────┘                    ▼
                                      │                  ┌───────────────┐
                                      ▼                  │  results/     │
                             ┌────────────────┐          │  <run_id>/    │
                             │  Metrics +     │─────────►│  report.html  │
                             │  HTML Reports  │          │  metrics.json │
                             └────────────────┘          └───────────────┘
```

### Components

| Module | Purpose |
|---|---|
| `qrp_platform/data/loader.py` | Pull OHLCV from `yfinance`, cache as CSV/Parquet |
| `qrp_platform/data/store.py` | Parquet-backed time-series store |
| `qrp_platform/strategies/` | Plugin strategies (`momentum`, `mean_reversion`, `multi_factor`) |
| `qrp_platform/backtest/engine.py` | Walk-forward engine, vectorised |
| `qrp_platform/backtest/metrics.py` | Sharpe, Sortino, Calmar, max DD, turnover, hit rate |
| `qrp_platform/backtest/reports.py` | HTML reports with Plotly charts |
| `qrp_platform/live/paper.py` | Paper trading loop (simulates broker) |
| `qrp_platform/live/scheduler.py` | APScheduler cron jobs |
| `qrp_platform/api/main.py` | FastAPI service |
| `qrp_platform/dashboard/app.py` | Streamlit dashboard |

---

## 🎯 Use cases

1. **Strategy research** — write a strategy class, backtest it, get an HTML report with metrics in 30 seconds.
2. **Walk-forward validation** — split data into train/test windows, aggregate out-of-sample metrics.
3. **Paper trading** — schedule a strategy to rebalance weekly and track live PnL against a simulated book.
4. **Strategy comparison** — run multiple strategies side-by-side via the dashboard.
5. **API-first deployment** — trigger backtests from a notebook, a CI pipeline, or another service.

---

## 🚀 Quickstart

### Local (no Docker)

```bash
git clone https://github.com/JoshRiang/quant-research-qrp_platform.git
cd quant-research-platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r qrp_platform/dashboard/requirements.txt

# Run a momentum backtest (writes to ./results/)
python examples/run_momentum_backtest.py

# Run the API
uvicorn qrp_platform.api.main:app --reload --port 8000

# Run the dashboard (separate terminal)
streamlit run qrp_platform/dashboard/app.py
```

### Docker (recommended)

```bash
docker compose up --build
```

Then open:
- Dashboard → http://localhost:8501
- API → http://localhost:8000/docs

---

## 🧠 Adding a new strategy

The platform auto-discovers any class that subclasses `qrp_platform.strategies.base.Strategy` in the `strategies/` directory.

### 1. Create the file

```python
# qrp_platform/strategies/my_breakout.py
from .base import Strategy
import pandas as pd

class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    description = "Buy when price breaks 20-day high."

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # df has columns: open, high, low, close, volume (indexed by date)
        high = df["high"].rolling(self.lookback).max()
        signal = (df["close"] > high.shift(1)).astype(int)
        out = pd.DataFrame(index=df.index)
        out["weight"] = signal  # long-only, full allocation
        return out
```

### 2. Use it immediately

```python
from qrp_platform.strategies import get_strategy
from qrp_platform.backtest.engine import BacktestEngine
from qrp_platform.data.loader import DataLoader

strat = get_strategy("donchian_breakout")
loader = DataLoader()
data = loader.load(["AAPL", "MSFT"], "2020-01-01", "2024-01-01")

engine = BacktestEngine(initial_capital=100_000)
result = engine.run(strat, data)
result.save_report("results/")
```

The strategy is auto-registered via the `_STRATEGY_REGISTRY` populated at import time. **No config edits required.**

---

## 📊 Backtest metrics

| Metric | Description |
|---|---|
| `total_return` | Cumulative return over the period |
| `cagr` | Compound annual growth rate |
| `sharpe` | Annualised Sharpe ratio (rf=0) |
| `sortino` | Annualised Sortino (downside deviation only) |
| `max_drawdown` | Largest peak-to-trough equity decline |
| `calmar` | CAGR / |max DD| |
| `volatility` | Annualised return std-dev |
| `hit_rate` | Fraction of positive return days |
| `turnover` | Average daily turnover (0–1) |
| `equity_final` | Final portfolio value |

Reports: `results/<run_id>/metrics.json` + `results/<run_id>/report.html`

---

## 🤖 Paper trading

```python
from qrp_platform.live.paper import PaperBroker
from qrp_platform.strategies import get_strategy

broker = PaperBroker(capital=100_000)
strat = get_strategy("momentum")  # 12-1 momentum
broker.run_one_tick(strat, ["AAPL", "MSFT", "NVDA"])  # single rebalance
print(broker.equity(), broker.positions())
```

For continuous operation:

```bash
# Run via docker-compose (scheduler service)
docker compose up scheduler
```

The scheduler rebalances every Monday at market open (configurable via `PAPER_CRON` env var).

---

## 🔌 API reference

`GET /health`
```json
{"status": "ok", "strategies": 3}
```

`GET /strategies`
```json
[
  {"name": "momentum", "description": "12-1 momentum"},
  {"name": "mean_reversion", "description": "Z-score mean reversion"},
  {"name": "multi_factor", "description": "Composite value/momentum/quality"}
]
```

`POST /backtest`
```json
{
  "strategy": "momentum",
  "tickers": ["AAPL","MSFT","SPY"],
  "start": "2020-01-01",
  "end":   "2024-01-01",
  "capital": 100000
}
```
Returns: `{run_id, metrics, report_url}`.

Interactive docs at `http://localhost:8000/docs`.

---

## ⚙️ Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `PAPER_CAPITAL` | `100000` | Paper trading starting capital |
| `DATA_DIR` | `./data` | Where to cache CSVs and Parquet |
| `RESULTS_DIR` | `./results` | Where to save backtest artifacts |
| `PAPER_CRON` | `0 9 * * 1-5` | Scheduler cron (9am Mon–Fri) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `API_HOST` | `0.0.0.0` | API bind host |
| `API_PORT` | `8000` | API bind port |

---

## 🐳 Deployment

### Docker Compose (full stack)

```bash
docker compose up --build
# api → :8000, dashboard → :8501, scheduler → background
```

### Production build

```bash
docker build --target production -t quant-research-platform:latest .
docker run -p 8000:8000 -p 8501:8501 quant-research-platform:latest
```

The Dockerfile has two stages:
- `dev` — installs full toolchain, runs as root, mounts source for hot reload.
- `production` — slim, non-root, `--workers 2`.

---

## 🧪 Tests

```bash
pytest -q tests
```

Smoke test (`tests/test_smoke.py`) exercises:
- Backtest end-to-end on `momentum`
- FastAPI `/health` returns 200
- Paper broker single tick completes without exception

---

## 📂 Layout

```
quant-research-qrp_platform/
├── qrp_platform/
│   ├── api/             # FastAPI service
│   ├── backtest/        # Engine + metrics + reports
│   ├── dashboard/       # Streamlit app
│   ├── data/            # yfinance loader + Parquet store
│   ├── live/            # Paper broker + scheduler
│   ├── strategies/      # Plugin strategies
│   └── config.py        # Pydantic settings
├── tests/
├── examples/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 📜 License

MIT — use freely, attribution appreciated.