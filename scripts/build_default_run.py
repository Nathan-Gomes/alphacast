"""Precompute the default workspace from the frozen snapshot.

The web app loads this file at start-up, so the first visitor sees a complete
workspace without waiting for five models to walk forward on a small instance.

    python scripts/build_default_run.py
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

from alphacast.config import ResearchConfig
from alphacast.data import snapshot_prices
from alphacast.runs import DEFAULT_RUN_FILE, RunRequest, execute
from alphacast.universe import UNIVERSES

OUTPUT = Path(__file__).resolve().parents[1] / "src" / "alphacast" / "snapshots" / DEFAULT_RUN_FILE


def main() -> None:
    end = snapshot_prices().date.max().date().isoformat()
    request = RunRequest(
        source="snapshot",
        tickers=list(UNIVERSES["us_large_cap"]["tickers"]),
        universe="us_large_cap",
        config=ResearchConfig(end=end),
        name="Default workspace",
    )
    started = time.time()
    workspace, securities = execute(
        request, lambda fraction, message: print(f"{fraction:5.0%}  {message}", flush=True)
    )
    payload = {"request": request.describe(), "workspace": workspace, "securities": securities}
    OUTPUT.write_bytes(gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), 9))
    print(f"Wrote {OUTPUT.name} ({OUTPUT.stat().st_size / 1e6:.1f} MB) in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
