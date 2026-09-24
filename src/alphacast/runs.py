"""In-process run registry: background research jobs and the shipped default workspace."""

from __future__ import annotations

import gzip
import json
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources

import pandas as pd

from .config import ResearchConfig
from .data import snapshot_prices, synthetic_prices, yahoo_prices
from .research import run_research
from .universe import UNIVERSES, sectors_for

DEFAULT_RUN_ID = "default"
DEFAULT_RUN_FILE = "default_run.json.gz"
MAX_RUNS = 12
# The public instance is small; a short queue keeps one visitor from starving others.
MAX_ACTIVE_RUNS = 3


class QueueFull(RuntimeError):
    """Raised when too many runs are already queued or running."""


@dataclass
class RunRequest:
    source: str
    tickers: list[str]
    universe: str
    config: ResearchConfig
    name: str

    def describe(self) -> dict[str, object]:
        return {
            "source": self.source,
            "universe": self.universe,
            "tickers": len(self.tickers),
            "models": list(self.config.models),
            "start": self.config.start,
            "end": self.config.end,
            "top_n": self.config.top_n,
            "max_per_sector": self.config.max_per_sector,
            "rebalance_every_folds": self.config.rebalance_every_folds,
            "hold_buffer": self.config.hold_buffer,
            "neutralize_volatility": self.config.neutralize_volatility,
            "transaction_cost_bps": self.config.transaction_cost_bps,
        }


@dataclass
class RunRecord:
    id: str
    name: str
    status: str
    request: dict[str, object]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    progress: float = 0.0
    message: str = "Queued"
    error: str | None = None
    workspace: dict[str, object] | None = None
    securities: dict[str, dict[str, object]] | None = None
    finished_at: str | None = None

    def meta(self) -> dict[str, object]:
        workspace = self.workspace or {}
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "request": self.request,
            "signal_date": workspace.get("signal_date"),
            "dataset": workspace.get("dataset"),
            "headline": _headline(workspace),
        }


def _headline(workspace: dict[str, object]) -> dict[str, object] | None:
    """The strongest model by mean Rank IC, so runs can be compared in a list."""
    summaries = workspace.get("summaries") or []
    if not summaries:
        return None
    best = max(summaries, key=lambda row: row["mean_rank_ic"])
    return {
        "model": best["model"],
        "label": best.get("label", best["model"]),
        "mean_rank_ic": best["mean_rank_ic"],
        "ic_t_stat": best["ic_t_stat"],
        "net_sharpe": best["net_sharpe"],
        "benchmark_sharpe": best["benchmark_sharpe"],
        "mean_turnover": best["mean_turnover"],
    }


def dataset_label(source: str, universe: str, tickers: int) -> str:
    base = UNIVERSES.get(universe, {}).get("label", f"Custom {tickers}")
    return {
        "snapshot": f"{base} · frozen Yahoo snapshot",
        "yahoo": f"{base} · live Yahoo Finance",
        "synthetic": "Synthetic 60 · simulated panel",
    }[source]


def load_prices(request: RunRequest) -> pd.DataFrame:
    if request.source == "synthetic":
        return synthetic_prices()
    if request.source == "snapshot":
        return snapshot_prices(request.tickers)
    return yahoo_prices(
        request.tickers,
        sectors_for(request.tickers),
        start=request.config.start,
        end=request.config.end,
    )


def execute(request: RunRequest, progress=None) -> tuple[dict[str, object], dict[str, object]]:
    """Run one request to completion and return the workspace and per-security payloads."""
    notify = progress or (lambda fraction, message: None)
    notify(0.01, "Loading Yahoo Finance history" if request.source == "yahoo" else "Loading prices")
    prices = load_prices(request)
    if request.source != "synthetic":
        unavailable = prices.attrs.get("unavailable_tickers", [])
        prices = prices[
            (prices.date >= pd.Timestamp(request.config.start))
            & (prices.date <= pd.Timestamp(request.config.end))
        ].copy()
        prices.attrs["unavailable_tickers"] = unavailable
    run = run_research(
        prices,
        source=request.source,
        config=request.config,
        dataset=dataset_label(request.source, request.universe, len(request.tickers)),
        progress=notify,
    )
    return run.to_dict(), run.security_details()


class RunRegistry:
    """Holds recent runs in memory and executes new ones one at a time."""

    def __init__(self) -> None:
        self._runs: OrderedDict[str, RunRecord] = OrderedDict()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alphacast-run")
        self._load_default()

    def _load_default(self) -> None:
        try:
            source = resources.files("alphacast.snapshots").joinpath(DEFAULT_RUN_FILE)
            with source.open("rb") as handle:
                payload = json.loads(gzip.decompress(handle.read()))
        except (FileNotFoundError, OSError):
            return
        self._runs[DEFAULT_RUN_ID] = RunRecord(
            id=DEFAULT_RUN_ID,
            name="Default workspace",
            status="complete",
            request=payload["request"],
            created_at=payload["workspace"]["created_at"],
            finished_at=payload["workspace"]["created_at"],
            progress=1.0,
            message="Precomputed from the frozen snapshot",
            workspace=payload["workspace"],
            securities=payload["securities"],
        )

    def list(self) -> list[dict[str, object]]:
        with self._lock:
            return [record.meta() for record in reversed(self._runs.values())]

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def submit(self, request: RunRequest) -> RunRecord:
        record = RunRecord(
            id=uuid.uuid4().hex[:10], name=request.name, status="queued", request=request.describe()
        )
        with self._lock:
            active = sum(run.status in {"queued", "running"} for run in self._runs.values())
            if active >= MAX_ACTIVE_RUNS:
                raise QueueFull(
                    f"{active} runs are already queued or running. Try again when one finishes."
                )
            self._runs[record.id] = record
            self._evict()
        self._executor.submit(self._run, record, request)
        return record

    def _evict(self) -> None:
        removable = [
            run_id
            for run_id, record in self._runs.items()
            if run_id != DEFAULT_RUN_ID and record.status in {"complete", "failed"}
        ]
        while len(self._runs) > MAX_RUNS and removable:
            self._runs.pop(removable.pop(0))

    def _run(self, record: RunRecord, request: RunRequest) -> None:
        def progress(fraction: float, message: str) -> None:
            record.progress = max(record.progress, min(fraction, 0.99))
            record.message = message

        record.status = "running"
        try:
            record.workspace, record.securities = execute(request, progress)
            record.status = "complete"
            record.progress = 1.0
            record.message = "Complete"
        except Exception as exc:  # noqa: BLE001 - every failure must reach the interface
            record.status = "failed"
            record.error = str(exc) or exc.__class__.__name__
            record.message = "Failed"
        finally:
            record.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
