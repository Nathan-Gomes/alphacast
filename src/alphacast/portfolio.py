"""Portfolio accounting for a score-ranked, equal-weight long-only sleeve."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PortfolioStep:
    gross_return: float
    net_return: float
    benchmark_return: float
    turnover: float
    transaction_cost: float
    holdings: tuple[str, ...]


def top_ranked_portfolio(
    rows: pd.DataFrame,
    scores: pd.Series,
    previous_weights: pd.Series | None,
    *,
    top_n: int,
    transaction_cost_bps: float,
) -> tuple[PortfolioStep, pd.Series]:
    """Construct a top-ranked equal-weight sleeve and charge one-way turnover costs."""
    if top_n < 1:
        raise ValueError("top_n must be positive.")
    ranked = rows.assign(score=scores).sort_values("score", ascending=False)
    selected = ranked.head(min(top_n, len(ranked))).copy()
    weights = pd.Series(1.0 / len(selected), index=selected.ticker, dtype=float)
    if previous_weights is None:
        turnover = 0.0
    else:
        aligned = pd.concat([weights.rename("new"), previous_weights.rename("old")], axis=1).fillna(0.0)
        turnover = float((aligned["new"] - aligned["old"]).abs().sum() / 2)
    cost = turnover * transaction_cost_bps / 10_000
    gross = float(selected.set_index("ticker").loc[weights.index, "forward_return_20"].dot(weights))
    benchmark = float(rows.forward_return_20.mean())
    return (
        PortfolioStep(
            gross_return=gross,
            net_return=gross - cost,
            benchmark_return=benchmark,
            turnover=turnover,
            transaction_cost=cost,
            holdings=tuple(weights.index),
        ),
        weights,
    )
