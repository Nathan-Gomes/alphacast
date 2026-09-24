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


def select_top(
    rows: pd.DataFrame, scores: pd.Series, *, top_n: int, max_per_sector: int | None = None
) -> pd.DataFrame:
    """The highest-scored rows, skipping a name once its sector already holds the cap.

    Without a cap this is simply the top ``top_n``. With one, lower-ranked names from
    other sectors fill the places, so the sleeve always holds ``top_n`` when it can.
    """
    if top_n < 1:
        raise ValueError("top_n must be positive.")
    ranked = rows.assign(score=scores).sort_values("score", ascending=False, kind="stable")
    if not max_per_sector:
        return ranked.head(min(top_n, len(ranked))).copy()
    within_sector = ranked.groupby("sector").cumcount()
    return ranked.loc[within_sector < max_per_sector].head(top_n).copy()


def top_ranked_portfolio(
    rows: pd.DataFrame,
    scores: pd.Series,
    previous_weights: pd.Series | None,
    *,
    top_n: int,
    transaction_cost_bps: float,
    max_per_sector: int | None = None,
) -> tuple[PortfolioStep, pd.Series]:
    """Construct a top-ranked equal-weight sleeve and charge one-way turnover costs."""
    selected = select_top(rows, scores, top_n=top_n, max_per_sector=max_per_sector)
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
