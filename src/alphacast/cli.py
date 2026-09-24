"""Command-line entry point for reproducible AlphaCast research runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import SUPPORTED_MODELS, ResearchConfig
from .runs import RunRequest, execute
from .universe import UNIVERSES


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Run an embargoed AlphaCast ranking study.")
    command.add_argument("--source", choices=("snapshot", "yahoo", "synthetic"), default="snapshot")
    command.add_argument("--universe", choices=tuple(UNIVERSES), default="us_large_cap")
    command.add_argument("--tickers", default="", help="Comma-separated; overrides --universe (Yahoo only)")
    command.add_argument("--start", default="2014-01-01")
    command.add_argument("--end", default=None)
    command.add_argument("--models", default=",".join(SUPPORTED_MODELS))
    command.add_argument("--top-n", type=int, default=15)
    command.add_argument("--cost-bps", type=float, default=10.0)
    command.add_argument("--output", type=Path, default=Path("output/latest-run.json"))
    return command


def main() -> None:
    args = parser().parse_args()
    models = tuple(model.strip() for model in args.models.split(",") if model.strip())
    config = ResearchConfig(
        start=args.start,
        end=args.end or ResearchConfig().end,
        models=models,
        top_n=args.top_n,
        transaction_cost_bps=args.cost_bps,
    )
    custom = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    tickers = custom or list(UNIVERSES[args.universe]["tickers"])
    universe = "custom" if custom else args.universe
    request = RunRequest(args.source, tickers, universe, config, "cli")
    workspace, _ = execute(request, lambda fraction, message: print(f"{fraction:5.0%}  {message}"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(workspace, indent=2), encoding="utf-8")
    print()
    for row in sorted(workspace["summaries"], key=lambda item: -item["mean_rank_ic"]):
        print(
            f"{row['label']:<20} IC {row['mean_rank_ic']:+.4f}  t {row['ic_t_stat']:+.2f}  "
            f"net Sharpe {row['net_sharpe']:.2f}  turnover {row['mean_turnover']:.0%}"
        )
    print(f"\nWrote the workspace record to {args.output}")


if __name__ == "__main__":
    main()
