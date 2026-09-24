"""AlphaCast web application: research API plus the workstation interface."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .config import MODEL_LABELS, SUPPORTED_MODELS, ResearchConfig
from .features import FEATURE_LABELS
from .ranking import model_specs
from .runs import DEFAULT_RUN_ID, QueueFull, RunRegistry, RunRequest
from .universe import UNIVERSES

WEB_DIRECTORY = Path(__file__).with_name("web")
MAX_TICKERS = 150
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,11}$")
# Seconds per model for a 98-stock snapshot run on a multi-core laptop. The interface
# multiplies them by SPEED_FACTOR, set per deployment, to show an honest estimate.
MODEL_SECONDS = {
    "momentum": 2, "ridge": 3, "elastic_net": 6, "random_forest": 17, "gradient_boosting": 21,
    "ensemble": 0,
}
# Render sets RENDER=true; its small instances are roughly ten times slower.
SPEED_FACTOR = float(os.environ.get("ALPHACAST_SPEED_FACTOR") or (12 if os.environ.get("RENDER") else 1.5))


class RunPayload(BaseModel):
    name: str = Field(default="", max_length=60)
    source: str = Field(default="snapshot", pattern="^(snapshot|yahoo|synthetic)$")
    universe: str = Field(default="us_large_cap", pattern="^(us_large_cap|starter_30|custom)$")
    tickers: list[str] = Field(default_factory=list)
    start: str = "2014-01-01"
    end: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    models: list[str] = Field(default_factory=lambda: list(SUPPORTED_MODELS))
    top_n: int = Field(default=15, ge=3, le=40)
    max_per_sector: int | None = Field(default=None, ge=1, le=20)
    rebalance_every_folds: int = Field(default=1, ge=1, le=3)
    hold_buffer: int | None = Field(default=None, ge=1, le=150)
    transaction_cost_bps: float = Field(default=10.0, ge=0, le=250)

    @field_validator("start", "end")
    @classmethod
    def iso_date(cls, value: str) -> str:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError("Dates must be YYYY-MM-DD.") from exc


app = FastAPI(title="AlphaCast", version=__version__, docs_url="/api/docs", redoc_url=None)


def _content_security_policy() -> str:
    """Allow the page's own inline theme script by hash, and nothing else inline."""
    html = (WEB_DIRECTORY / "index.html").read_text(encoding="utf-8")
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'"
        for script in re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    )
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {hashes}",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )


CONTENT_SECURITY_POLICY = _content_security_policy()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path == "/":
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if request.url.path.startswith("/assets/"):
        # File names are not content-hashed, so browsers must revalidate (cheap, via
        # ETag) or a returning visitor could run stale scripts after a deploy.
        response.headers["Cache-Control"] = "no-cache"
    return response
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
        "commit": os.environ.get("RENDER_GIT_COMMIT", "")[:7] or None,
        "models": list(SUPPORTED_MODELS),
        "default_workspace": default is not None,
    }


@app.get("/api/catalog")
def catalog() -> dict[str, object]:
    """Everything the run form needs: universes, models, sources, features."""
    return {
        "universes": [{"id": key, **value} for key, value in UNIVERSES.items()],
        "models": [
            {
                "id": model,
                "label": MODEL_LABELS[model],
                "seconds": round(MODEL_SECONDS[model] * SPEED_FACTOR),
                "default": model in {"momentum", "ridge", "elastic_net", "ensemble"},
            }
            for model in SUPPORTED_MODELS
        ],
        "overhead_seconds": round(3 * SPEED_FACTOR),
        "model_specs": model_specs(),
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
    if "ensemble" in models and len(set(models) - {"momentum", "ensemble"}) < 2:
        raise HTTPException(422, "The ensemble combines other models: select at least two of Ridge, Elastic Net, Random Forest and Gradient Boosting.")
    if payload.start >= payload.end:
        raise HTTPException(422, "The start date must be before the end date.")
    if payload.hold_buffer is not None and payload.hold_buffer < payload.top_n:
        raise HTTPException(422, "The holding buffer must be at least the portfolio size.")
    if payload.universe == "custom":
        tickers = list(dict.fromkeys(t.upper().strip() for t in payload.tickers if t.strip()))
        invalid = [ticker for ticker in tickers if not TICKER_PATTERN.match(ticker)]
        if invalid:
            raise HTTPException(422, f"Not valid ticker symbols: {', '.join(invalid[:8])}.")
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
        max_per_sector=payload.max_per_sector,
        rebalance_every_folds=payload.rebalance_every_folds,
        hold_buffer=payload.hold_buffer,
    )
    name = payload.name.strip() or f"{payload.source.title()} · {len(models)} models"
    try:
        record = registry.submit(RunRequest(payload.source, tickers, payload.universe, config, name))
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc
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
