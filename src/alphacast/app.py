"""AlphaCast web application: research API plus the workstation interface."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .config import MODEL_LABELS, SUPPORTED_MODELS, ResearchConfig
from .features import FEATURE_LABELS
from .runs import DEFAULT_RUN_ID, RunRegistry, RunRequest, execute
from .universe import DEFAULT_UNIVERSE, UNIVERSES

WEB_DIRECTORY = Path(__file__).with_name("web")
MAX_TICKERS = 150


class RunPayload(BaseModel):
    name: str = Field(default="", max_length=60)
    source: str = Field(default="snapshot", pattern="^(snapshot|yahoo|synthetic)$")
    universe: str = Field(default="us_large_cap", pattern="^(us_large_cap|starter_30|custom)$")
    tickers: list[str] = Field(default_factory=list)
    start: str = "2014-01-01"
    end: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    models: list[str] = Field(default_factory=lambda: list(SUPPORTED_MODELS))
    top_n: int = Field(default=15, ge=3, le=40)
    transaction_cost_bps: float = Field(default=10.0, ge=0, le=250)

    @field_validator("start", "end")
    @classmethod
    def iso_date(cls, value: str) -> str:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError("Dates must be YYYY-MM-DD.") from exc


app = FastAPI(title="AlphaCast", version=__version__, docs_url="/api/docs", redoc_url=None)
app.mount("/assets", StaticFiles(directory=WEB_DIRECTORY), name="assets")
registry = RunRegistry()


@app.get("/", include_in_schema=False)
def workstation() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB_DIRECTORY / "favicon.svg")


@app.get("/api/health")
def health() -> dict[str, object]:
    default = registry.get(DEFAULT_RUN_ID)
    return {
        "status": "ok",
        "service": "alphacast",
        "version": __version__,
        "models": list(SUPPORTED_MODELS),
        "default_workspace": default is not None,
    }


@app.get("/api/catalog")
def catalog() -> dict[str, object]:
    """Everything the run form needs: universes, models, sources, features."""
    return {
        "universes": [{"id": key, **value} for key, value in UNIVERSES.items()],
        "models": [{"id": model, "label": MODEL_LABELS[model]} for model in SUPPORTED_MODELS],
        "features": [{"id": key, "label": value} for key, value in FEATURE_LABELS.items()],
        "sources": [
            {"id": "snapshot", "label": "Frozen snapshot", "detail": "Shipped Yahoo history. Instant and reproducible."},
            {"id": "yahoo", "label": "Live Yahoo Finance", "detail": "Downloads current history. Custom tickers allowed."},
            {"id": "synthetic", "label": "Synthetic panel", "detail": "Simulated 60-security panel for method checks."},
        ],
        "defaults": {"top_n": 15, "transaction_cost_bps": 10.0, "start": "2014-01-01"},
    }


@app.get("/api/runs")
def list_runs() -> dict[str, object]:
    return {"runs": registry.list()}


@app.post("/api/runs", status_code=202)
def create_run(payload: RunPayload) -> dict[str, object]:
    models = tuple(dict.fromkeys(model.strip() for model in payload.models if model.strip()))
    unknown = set(models) - set(SUPPORTED_MODELS)
    if unknown:
        raise HTTPException(422, f"Unsupported models: {', '.join(sorted(unknown))}")
    if not models:
        raise HTTPException(422, "Select at least one model.")
    if payload.start >= payload.end:
        raise HTTPException(422, "The start date must be before the end date.")
    if payload.universe == "custom":
        tickers = list(dict.fromkeys(t.upper().strip() for t in payload.tickers if t.strip()))
    else:
        tickers = list(UNIVERSES[payload.universe]["tickers"])
    if payload.source != "synthetic":
        if len(tickers) < 10:
            raise HTTPException(422, "A cross-sectional study needs at least ten tickers.")
        if len(tickers) > MAX_TICKERS:
            raise HTTPException(422, f"Use at most {MAX_TICKERS} tickers.")
    config = ResearchConfig(
        start=payload.start,
        end=payload.end,
        models=models,
        top_n=payload.top_n,
        transaction_cost_bps=payload.transaction_cost_bps,
    )
    name = payload.name.strip() or f"{payload.source.title()} · {len(models)} models"
    record = registry.submit(
        RunRequest(payload.source, tickers, payload.universe, config, name)
    )
    return record.meta()


def _record(run_id: str):
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(404, "Run not found. Runs are kept in memory and reset on restart.")
    return record


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    record = _record(run_id)
    return {**record.meta(), "workspace": record.workspace}


@app.get("/api/runs/{run_id}/securities/{ticker}")
def get_security(run_id: str, ticker: str) -> dict[str, object]:
    record = _record(run_id)
    if record.status != "complete" or not record.securities:
        raise HTTPException(409, "This run has not finished.")
    detail = record.securities.get(ticker.upper())
    if detail is None:
        raise HTTPException(404, f"{ticker.upper()} is not in this run.")
    return {"ticker": ticker.upper(), **detail}


@app.get("/api/universe", include_in_schema=False)
def legacy_universe() -> dict[str, object]:
    """Kept for the original single-page interface."""
    return {"tickers": DEFAULT_UNIVERSE, "count": len(DEFAULT_UNIVERSE)}


@app.post("/api/research", include_in_schema=False)
def legacy_research(payload: dict) -> dict[str, object]:
    """Synchronous run kept for the original single-page interface."""
    source = payload.get("source", "synthetic")
    tickers = [str(t).upper().strip() for t in payload.get("tickers", []) if str(t).strip()]
    models = tuple(payload.get("models") or SUPPORTED_MODELS)
    if set(models) - set(SUPPORTED_MODELS) or not models:
        raise HTTPException(422, "Select supported models.")
    config = ResearchConfig(
        start=payload.get("start", "2017-01-01"),
        end=payload.get("end", datetime.now(timezone.utc).date().isoformat()),
        models=models,
        top_n=int(payload.get("top_n", 10)),
        transaction_cost_bps=float(payload.get("transaction_cost_bps", 10.0)),
    )
    universe = "custom" if source == "yahoo" else "us_large_cap"
    if source == "yahoo" and len(tickers) < 10:
        raise HTTPException(422, "Yahoo studies need at least ten tickers.")
    request = RunRequest(source if source == "yahoo" else "synthetic", tickers, universe, config, "legacy")
    try:
        workspace, _ = execute(request)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    model_ids = [row["model"] for row in workspace["summaries"]]
    last = workspace["last_rebalance"]
    return {
        **workspace,
        "latest_rankings": [
            {**row, "date": last, "momentum_12_1": None, "volatility_20": None}
            for row in workspace["live"]
            if row["model"] in model_ids
        ],
    }


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: str) -> Response:
    record = _record(run_id)
    if record.status != "complete":
        raise HTTPException(409, "This run has not finished.")
    body = json.dumps({"run": record.meta(), "workspace": record.workspace}, indent=1)
    filename = f"alphacast-{record.id}-{(record.workspace or {}).get('signal_date', 'run')}.json"
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
