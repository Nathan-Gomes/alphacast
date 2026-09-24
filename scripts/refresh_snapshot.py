"""Re-download the frozen Yahoo Finance snapshot that ships with the package.

    python scripts/refresh_snapshot.py [--start 2014-01-01]

Rebuild the default workspace afterwards with scripts/build_default_run.py.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from alphacast.data import SNAPSHOT_FILE, drop_incomplete_sessions, yahoo_prices
from alphacast.universe import US_LARGE_CAP

OUTPUT = Path(__file__).resolve().parents[1] / "src" / "alphacast" / "snapshots" / SNAPSHOT_FILE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2014-01-01")
    parser.add_argument(
        "--min-tickers", type=int, default=95,
        help="refuse to write a snapshot with fewer securities than this",
    )
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    prices = yahoo_prices(list(US_LARGE_CAP), US_LARGE_CAP, start=args.start, end=args.end)
    prices, dropped = drop_incomplete_sessions(prices)
    if prices.ticker.nunique() < args.min_tickers:
        raise SystemExit(
            f"Only {prices.ticker.nunique()} tickers returned (need {args.min_tickers}); "
            "keeping the existing snapshot."
        )
    if OUTPUT.exists():
        import pandas as pd

        existing = pd.read_csv(OUTPUT, usecols=["date"])
        if existing.date.max() >= prices.date.max().strftime("%Y-%m-%d") and len(existing) >= len(prices):
            print(f"No new sessions after {existing.date.max()}; snapshot unchanged.")
            return
    prices.to_csv(
        OUTPUT, index=False, float_format="%.4f", date_format="%Y-%m-%d",
        compression={"method": "gzip", "mtime": 0},
    )
    print(
        f"Wrote {prices.ticker.nunique()} tickers, {prices.date.nunique()} sessions "
        f"({dropped} partial sessions dropped) to {OUTPUT.name}"
    )


if __name__ == "__main__":
    main()
