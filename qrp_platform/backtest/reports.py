"""HTML report generation with Plotly charts."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .engine import BacktestResult


def save_report(result: BacktestResult, out_dir: Path) -> Path:
    """Render an HTML report with equity curve, drawdown, and rolling metrics."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    equity = result.equity
    drawdown = equity / equity.cummax() - 1.0
    rolling_sharpe = (
        result.returns.rolling(63).mean() / result.returns.rolling(63).std() * (252 ** 0.5)
    )

    # Build Plotly figures as JSON for embedding
    equity_chart = _equity_figure(equity, result)
    dd_chart = _drawdown_figure(drawdown)
    rs_chart = _rolling_figure(rolling_sharpe)

    metrics_table = _metrics_table(result.metrics)

    html = _render_html(
        result=result,
        equity_chart=equity_chart,
        dd_chart=dd_chart,
        rs_chart=rs_chart,
        metrics_table=metrics_table,
    )

    report_path = out_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path


def _equity_figure(equity: pd.Series, result: BacktestResult) -> str:
    dates = [d.strftime("%Y-%m-%d") for d in equity.index]
    values = [float(v) for v in equity.values]
    data = [
        {
            "x": dates,
            "y": values,
            "type": "scatter",
            "mode": "lines",
            "name": "Equity",
            "line": {"color": "#2196F3", "width": 2},
            "fill": "tozeroy",
            "fillcolor": "rgba(33,150,243,0.10)",
        }
    ]
    layout = {
        "title": f"Equity Curve — {result.strategy_name}",
        "xaxis": {"title": "Date"},
        "yaxis": {"title": "Portfolio Value ($)"},
        "margin": {"l": 60, "r": 30, "t": 50, "b": 50},
    }
    return _plotly_div(data, layout)


def _drawdown_figure(drawdown: pd.Series) -> str:
    dates = [d.strftime("%Y-%m-%d") for d in drawdown.index]
    values = [float(v) for v in drawdown.values]
    data = [
        {
            "x": dates,
            "y": values,
            "type": "scatter",
            "mode": "lines",
            "name": "Drawdown",
            "line": {"color": "#E53935", "width": 1.5},
            "fill": "tozeroy",
            "fillcolor": "rgba(229,57,53,0.15)",
        }
    ]
    layout = {
        "title": "Drawdown",
        "xaxis": {"title": "Date"},
        "yaxis": {"title": "Drawdown", "tickformat": ".0%"},
        "margin": {"l": 60, "r": 30, "t": 50, "b": 50},
    }
    return _plotly_div(data, layout)


def _rolling_figure(rolling: pd.Series) -> str:
    dates = [d.strftime("%Y-%m-%d") for d in rolling.index]
    values = [float(v) if v == v else None for v in rolling.values]  # nan -> None
    data = [
        {
            "x": dates,
            "y": values,
            "type": "scatter",
            "mode": "lines",
            "name": "Rolling Sharpe (63d)",
            "line": {"color": "#43A047", "width": 1.5},
        }
    ]
    layout = {
        "title": "Rolling Sharpe (63-day)",
        "xaxis": {"title": "Date"},
        "yaxis": {"title": "Sharpe"},
        "margin": {"l": 60, "r": 30, "t": 50, "b": 50},
    }
    return _plotly_div(data, layout)


def _metrics_table(metrics: dict[str, float]) -> str:
    rows = []
    pretty_names = {
        "total_return": "Total Return",
        "cagr": "CAGR",
        "sharpe": "Sharpe Ratio",
        "sortino": "Sortino Ratio",
        "max_drawdown": "Max Drawdown",
        "calmar": "Calmar Ratio",
        "volatility": "Volatility",
        "hit_rate": "Hit Rate",
        "turnover": "Avg Turnover",
        "equity_final": "Final Equity",
    }
    for key, label in pretty_names.items():
        if key in metrics:
            v = metrics[key]
            if key in ("total_return", "cagr", "max_drawdown", "volatility", "hit_rate", "turnover"):
                v_str = f"{v:.2%}"
            elif key == "equity_final":
                v_str = f"${v:,.0f}"
            else:
                v_str = f"{v:.3f}"
            rows.append(f"<tr><td>{label}</td><td>{v_str}</td></tr>")
    # OOS metrics
    for key, v in metrics.items():
        if key.startswith("oos_") and key not in {f"oos_{k}" for k in pretty_names}:
            label = "OOS " + key[4:].replace("_", " ").title()
            if key in ("oos_total_return", "oos_cagr", "oos_max_drawdown",
                       "oos_volatility", "oos_hit_rate", "oos_turnover"):
                v_str = f"{v:.2%}"
            elif key == "oos_equity_final":
                v_str = f"${v:,.0f}"
            else:
                v_str = f"{v:.3f}"
            rows.append(f"<tr><td>{label}</td><td>{v_str}</td></tr>")

    return (
        "<table class='metrics'>"
        "<thead><tr><th>Metric</th><th>Value</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _plotly_div(data, layout) -> str:
    fig = {"data": data, "layout": layout}
    return f'<div class="plotly-chart" data-figure=\'{json.dumps(fig)}\'></div>'


def _render_html(
    result: BacktestResult,
    equity_chart: str,
    dd_chart: str,
    rs_chart: str,
    metrics_table: str,
) -> str:
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f1216; color: #e6e6e6; margin: 0; padding: 30px; }
    h1 { color: #fff; border-bottom: 1px solid #2a2f37; padding-bottom: 12px; }
    h2 { color: #cfd8dc; margin-top: 30px; }
    .meta { color: #90a4ae; font-size: 14px; margin-bottom: 20px; }
    table.metrics { border-collapse: collapse; min-width: 320px; }
    table.metrics th, table.metrics td { padding: 8px 14px; text-align: left;
        border-bottom: 1px solid #2a2f37; }
    table.metrics th { background: #1a1f25; color: #fff; }
    table.metrics tr:hover { background: #1a1f25; }
    .plotly-chart { background: #1a1f25; border-radius: 8px; padding: 16px;
        margin: 16px 0; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    """
    head = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Backtest Report</title>"
        f"<style>{css}</style>"
        "<script src='https://cdn.plot.ly/plotly-2.27.0.min.js'></script>"
        "</head><body>"
    )

    body = f"""
    <h1>Backtest Report — {result.strategy_name}</h1>
    <div class='meta'>
      Run ID: <code>{result.run_id}</code><br>
      Period: {result.start} → {result.end} &nbsp;|&nbsp;
      Universe: {', '.join(result.tickers)} &nbsp;|&nbsp;
      Capital: ${result.initial_capital:,.0f}
    </div>
    {metrics_table}
    <h2>Equity Curve</h2>
    {equity_chart}
    <div class='grid'>
      <div>{dd_chart}</div>
      <div>{rs_chart}</div>
    </div>
    <script>
      document.querySelectorAll('.plotly-chart').forEach(el => {{
        const fig = JSON.parse(el.getAttribute('data-figure'));
        Plotly.newPlot(el, fig.data, fig.layout, {{responsive: true, displayModeBar: false}});
      }});
    </script>
    </body></html>
    """
    return head + body