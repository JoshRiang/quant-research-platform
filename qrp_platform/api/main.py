"""FastAPI app exposing strategy registry, health, and a backtest endpoint."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from qrp_platform.backtest.engine import BacktestEngine
from qrp_platform.config import settings
from qrp_platform.data.loader import DataLoader
from qrp_platform.strategies import get_strategy, list_strategies

app = FastAPI(
    title="Quant Research Platform API",
    version="0.1.0",
    description="Strategy registry, backtests, and health endpoints.",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="Registered strategy name")
    tickers: list[str] = Field(..., min_length=1)
    start: Optional[str] = None
    end: Optional[str] = None
    capital: float = 100_000.0
    walk_forward: bool = False


class BacktestResponse(BaseModel):
    run_id: str
    strategy: str
    metrics: dict[str, float]
    report_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "strategies": len(list_strategies())}


@app.get("/strategies")
def strategies() -> list[dict[str, str]]:
    return list_strategies()


@app.post("/backtest", response_model=BacktestResponse)
def backtest(req: BacktestRequest) -> BacktestResponse:
    try:
        strat = get_strategy(req.strategy)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    loader = DataLoader()
    start = req.start or settings.default_start
    end = req.end or settings.default_end
    data = loader.load(req.tickers, start=start, end=end)

    if not data:
        raise HTTPException(status_code=400, detail="No data returned for tickers")

    engine = BacktestEngine(
        initial_capital=req.capital,
        walk_forward=req.walk_forward,
    )
    result = engine.run(strat, data, start=start, end=end)
    out_dir = engine.save(result)
    report_path = out_dir / "report.html"
    return BacktestResponse(
        run_id=result.run_id,
        strategy=result.strategy_name,
        metrics=result.metrics,
        report_url=str(report_path) if report_path.exists() else None,
    )


@app.get("/")
def root() -> dict:
    return {
        "service": "quant-research-platform",
        "version": "0.1.0",
        "endpoints": ["/health", "/strategies", "/backtest", "/docs"],
    }