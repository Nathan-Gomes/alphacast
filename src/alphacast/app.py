"""Local research dashboard API for AlphaCast."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import SUPPORTED_MODELS, ResearchConfig
from .data import synthetic_prices, yahoo_prices
from .research import run_research
from .universe import DEFAULT_UNIVERSE, sectors_for


class ResearchRequest(BaseModel):
    source: str = Field(default="synthetic", pattern="^(synthetic|yahoo)$")
    tickers: list[str] = Field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    start: str = "2017-01-01"
    end: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    models: list[str] = Field(default_factory=lambda: list(SUPPORTED_MODELS))
    top_n: int = Field(default=10, ge=1, le=30)
    transaction_cost_bps: float = Field(default=10.0, ge=0, le=250)


app = FastAPI(title="AlphaCast", version="0.2.0")
WEB_DIRECTORY = Path(__file__).with_name("web")


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "index.html")


@app.get("/assets/{asset}", include_in_schema=False)
def asset(asset: str) -> FileResponse:
    path = WEB_DIRECTORY / asset
    if not path.is_file() or path.parent != WEB_DIRECTORY:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(path)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "alphacast",
        "default_source": "synthetic",
        "models": list(SUPPORTED_MODELS),
        "note": "Yahoo is supported on demand; synthetic is the transparent default demonstration.",
    }


@app.get("/api/universe")
def universe() -> dict[str, object]:
    return {"tickers": DEFAULT_UNIVERSE, "count": len(DEFAULT_UNIVERSE)}


@app.post("/api/research")
def research(request: ResearchRequest) -> dict[str, object]:
    models = tuple(model.strip() for model in request.models if model.strip())
    unknown = set(models) - set(SUPPORTED_MODELS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported models: {', '.join(sorted(unknown))}")
    if not models:
        raise HTTPException(status_code=422, detail="Select at least one model.")
    tickers = list(dict.fromkeys(ticker.upper().strip() for ticker in request.tickers if ticker.strip()))
    if request.source == "yahoo" and len(tickers) < 10:
        raise HTTPException(status_code=422, detail="Yahoo studies need at least ten tickers.")
    config = ResearchConfig(
        start=request.start,
        end=request.end,
        models=models,
        top_n=request.top_n,
        transaction_cost_bps=request.transaction_cost_bps,
    )
    try:
        prices = (
            synthetic_prices()
            if request.source == "synthetic"
            else yahoo_prices(tickers, sectors_for(tickers), start=config.start, end=config.end)
        )
        return run_research(prices, source=request.source, config=config).to_dict()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
