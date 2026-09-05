"""Streamlit dashboard for the Quant Research Platform.

Run:
    streamlit run platform/dashboard/app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from qrp_platform.backtest.engine import BacktestEngine
from qrp_platform.config import settings
from qrp_platform.data.loader import DataLoader
from qrp_platform.strategies import list_strategies

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_URL = st.sidebar.text_input("API URL", value="http://localhost:8000")

st.set_page_config(
    page_title="Quant Research Platform",
    page_icon="📈",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fetch_strategies() -> list[dict[str, str]]:
    try:
        r = requests.get(f"{API_URL}/strategies", timeout=3)
        r.raise_for_status()
        return r.json()
    except Exception:
        # Fallback to local registry
        return list_strategies()


def _post_backtest(payload: dict) -> dict:
    r = requests.post(f"{API_URL}/backtest", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


def _list_runs(results_dir: Path) -> list[Path]:
    if not results_dir.exists():
        return []
    return sorted([p for p in results_dir.iterdir() if p.is_dir()], reverse=True)


def _load_metrics(run_dir: Path) -> dict | None:
    p = run_dir / "metrics.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📊 QRP")
page = st.sidebar.radio("Navigate", ["Backtest Runner", "Run History", "Strategy Catalog"])


# ---------------------------------------------------------------------------
# Page: Backtest Runner
# ---------------------------------------------------------------------------
if page == "Backtest Runner":
    st.title("Backtest Runner")
    st.caption("Pick a strategy, universe, and date range; get metrics + report on disk.")

    strategies = _fetch_strategies()
    if not strategies:
        st.warning("No strategies registered.")
        st.stop()

    with st.form("backtest_form"):
        col1, col2 = st.columns(2)
        with col1:
            strat_name = st.selectbox(
                "Strategy",
                [s["name"] for s in strategies],
                help="Auto-registered from platform/strategies/",
            )
            tickers_raw = st.text_input("Tickers (comma-separated)", "AAPL, MSFT, SPY, NVDA")
            capital = st.number_input("Initial capital ($)", min_value=1000, value=100_000, step=1000)
        with col2:
            start = st.date_input("Start", pd.Timestamp("2020-01-01"))
            end = st.date_input("End", pd.Timestamp("2024-01-01"))
            walk_forward = st.checkbox("Walk-forward validation")

        submitted = st.form_submit_button("Run backtest", use_container_width=True)

    if submitted:
        tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
        if not tickers:
            st.error("Provide at least one ticker.")
        else:
            with st.spinner("Pulling data and running backtest…"):
                # Use the local engine (API may not be running)
                try:
                    from qrp_platform.strategies import get_strategy
                    strat = get_strategy(strat_name)
                    loader = DataLoader()
                    data = loader.load(tickers, str(start), str(end))
                    if not data:
                        st.error("Loader returned no data.")
                    else:
                        engine = BacktestEngine(initial_capital=capital, walk_forward=walk_forward)
                        result = engine.run(strat, data, str(start), str(end))
                        run_dir = engine.save(result)
                        st.success(f"Saved → {run_dir}")
                        st.session_state["last_run"] = (run_dir, result)
                except Exception as exc:
                    st.error(f"Backtest failed: {exc}")

    if "last_run" in st.session_state:
        run_dir, result = st.session_state["last_run"]
        st.subheader("Latest run metrics")
        m = result.metrics
        cols = st.columns(5)
        for i, (k, label) in enumerate(
            [
                ("total_return", "Total Return"),
                ("sharpe", "Sharpe"),
                ("sortino", "Sortino"),
                ("max_drawdown", "Max DD"),
                ("calmar", "Calmar"),
            ]
        ):
            with cols[i]:
                if k in m:
                    v = m[k]
                    if k == "max_drawdown":
                        st.metric(label, f"{v:.2%}")
                    elif k in ("total_return",):
                        st.metric(label, f"{v:.2%}")
                    else:
                        st.metric(label, f"{v:.3f}")
                else:
                    st.metric(label, "—")

        # Equity curve
        fig = px.line(result.equity, title="Equity Curve")
        fig.update_layout(template="plotly_dark", height=420)
        st.plotly_chart(fig, use_container_width=True)

        # Drawdown
        dd = result.equity / result.equity.cummax() - 1.0
        fig2 = px.area(dd, title="Drawdown")
        fig2.update_layout(template="plotly_dark", height=320)
        st.plotly_chart(fig2, use_container_width=True)

        # Weights heatmap
        st.subheader("Weight allocation over time")
        weights_sample = result.weights.iloc[::5]  # downsample for display
        fig3 = px.imshow(
            weights_sample.T,
            aspect="auto",
            color_continuous_scale="RdBu_r",
            title="Weights (downsampled)",
        )
        fig3.update_layout(template="plotly_dark", height=320)
        st.plotly_chart(fig3, use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Run History
# ---------------------------------------------------------------------------
elif page == "Run History":
    st.title("Run History")
    runs = _list_runs(settings.results_dir)
    if not runs:
        st.info("No backtest runs yet. Run one from the Backtest Runner tab.")
    else:
        rows = []
        for r in runs:
            m = _load_metrics(r) or {}
            rows.append(
                {
                    "run_id": m.get("run_id", r.name),
                    "strategy": m.get("strategy", "?"),
                    "start": m.get("start"),
                    "end": m.get("end"),
                    "sharpe": (m.get("metrics") or {}).get("sharpe"),
                    "total_return": (m.get("metrics") or {}).get("total_return"),
                    "max_dd": (m.get("metrics") or {}).get("max_drawdown"),
                    "report": str(r / "report.html") if (r / "report.html").exists() else None,
                    "metrics_json": str(r / "metrics.json"),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Strategy Catalog
# ---------------------------------------------------------------------------
elif page == "Strategy Catalog":
    st.title("Strategy Catalog")
    strategies = _fetch_strategies()
    st.write("Auto-registered from `platform/strategies/`. Add a new one by subclassing `Strategy`.")
    for s in strategies:
        with st.expander(f"**{s['name']}**"):
            st.write(s.get("description", "(no description)"))
            st.code(
                f"from qrp_platform.strategies import get_strategy\n"
                f"strat = get_strategy('{s['name']}')\n",
                language="python",
            )