"""Command-line entry point for reproducible AlphaCast research runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import SUPPORTED_MODELS, ResearchConfig
from .data import synthetic_prices, yahoo_prices
from .research import run_research
from .universe import DEFAULT_UNIVERSE, sectors_for


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Run an embargoed AlphaCast ranking study.")
    command.add_argument("--source", choices=("synthetic", "yahoo"), default="synthetic")
    command.add_argument("--tickers", default=",".join(DEFAULT_UNIVERSE))
    command.add_argument("--start", default="2017-01-01")
    command.add_argument("--end", default=None)
    command.add_argument("--models", default=",".join(SUPPORTED_MODELS))
    command.add_argument("--top-n", type=int, default=10)
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
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    prices = (
        synthetic_prices()
        if args.source == "synthetic"
        else yahoo_prices(tickers, sectors_for(tickers), start=config.start, end=config.end)
    )
    run = run_research(prices, source=args.source, config=config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")
    print(run.summaries.to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print(f"\nWrote reproducible run record to {args.output}")


if __name__ == "__main__":
    main()
