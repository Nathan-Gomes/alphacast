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
    rows: pd.DataFrame,
    scores: pd.Series,
    *,
    top_n: int,
    max_per_sector: int | None = None,
    keep: set[str] | None = None,
    keep_within: int | None = None,
) -> pd.DataFrame:
    """The highest-scored rows, with an optional sector cap and holding buffer.

    Without options this is simply the top ``top_n``. A cap skips a name once its sector
    holds ``max_per_sector``. A buffer keeps any name in ``keep`` (the current book)
    while it still ranks within ``keep_within``, and fills the remaining places from the
    top, so a stock is not sold just because it slipped from 15th to 17th.
    """
    if top_n < 1:
        raise ValueError("top_n must be positive.")
    ranked = rows.assign(score=scores).sort_values("score", ascending=False, kind="stable")
    ranked = ranked.assign(_position=range(len(ranked)))
    if not max_per_sector and not (keep and keep_within):
        return ranked.head(min(top_n, len(ranked))).drop(columns="_position").copy()
    chosen: list[int] = []
    per_sector: dict[str, int] = {}

    def take(frame: pd.DataFrame) -> None:
        for label, row in frame.iterrows():
            if len(chosen) >= top_n:
                return
            if label in chosen:
                continue
            if max_per_sector and per_sector.get(row.sector, 0) >= max_per_sector:
                continue
            chosen.append(label)
            per_sector[row.sector] = per_sector.get(row.sector, 0) + 1

    if keep and keep_within:
        take(ranked.loc[ranked.ticker.isin(keep) & (ranked._position < keep_within)])
    take(ranked)
    return ranked.loc[chosen].drop(columns="_position").copy()


def top_ranked_portfolio(
    rows: pd.DataFrame,
    scores: pd.Series,
    previous_weights: pd.Series | None,
    *,
    top_n: int,
    transaction_cost_bps: float,
    max_per_sector: int | None = None,
    hold_buffer: int | None = None,
) -> tuple[PortfolioStep, pd.Series]:
    """Construct a top-ranked equal-weight sleeve and charge one-way turnover costs."""
    selected = select_top(
        rows, scores, top_n=top_n, max_per_sector=max_per_sector,
        keep=set(previous_weights.index) if previous_weights is not None else None,
        keep_within=hold_buffer,
    )
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


def hold_portfolio(rows: pd.DataFrame, weights: pd.Series) -> PortfolioStep:
    """Carry the previous book through a month without trading: no turnover, no cost.

    Weights are kept at their rebalance values; drift between rebalances is ignored,
    as it is for the monthly sleeve's own holding period.
    """
    forward = rows.set_index("ticker").forward_return_20.reindex(weights.index).fillna(0.0)
    gross = float(forward.dot(weights))
    return PortfolioStep(
        gross_return=gross,
        net_return=gross,
        benchmark_return=float(rows.forward_return_20.mean()),
        turnover=0.0,
        transaction_cost=0.0,
        holdings=tuple(weights.index),
    )


def run_sleeve(
    cross_sections: list[tuple[pd.DataFrame, pd.Series]],
    *,
    top_n: int,
    transaction_cost_bps: float,
    rebalance_every: int = 1,
    max_per_sector: int | None = None,
    hold_buffer: int | None = None,
) -> list[tuple[PortfolioStep, pd.Series]]:
    """Walk a sleeve through consecutive (rows, scores) cross-sections.

    It rebalances every ``rebalance_every`` periods and holds the book unchanged in
    between. Each element is the period's step and the weights held over it.
    """
    weights: pd.Series | None = None
    path: list[tuple[PortfolioStep, pd.Series]] = []
    for position, (rows, scores) in enumerate(cross_sections):
        if weights is not None and position % max(rebalance_every, 1):
            step = hold_portfolio(rows, weights)
        else:
            step, weights = top_ranked_portfolio(
                rows, scores, weights, top_n=top_n, transaction_cost_bps=transaction_cost_bps,
                max_per_sector=max_per_sector, hold_buffer=hold_buffer,
            )
        path.append((step, weights))
    return path
