"""Chronological folds with an embargo for overlapping forward labels."""

from __future__ import annotations

import pandas as pd

from .contracts import WalkForwardFold, monthly_dates


def expanding_folds(
    panel: pd.DataFrame,
    minimum_train_sessions: int = 252,
    embargo_sessions: int = 20,
    calendar: pd.DatetimeIndex | None = None,
) -> list[WalkForwardFold]:
    """Monthly folds with an expanding training window.

    ``calendar`` is the full trading calendar. Month-ends come from it, so a month
    cut short by the missing labels at the end of the sample never becomes a fold.
    """
    dates = pd.DatetimeIndex(panel.date.unique()).sort_values()
    if len(dates) <= minimum_train_sessions + embargo_sessions:
        raise ValueError("Not enough completed history for an expanding, embargoed study.")
    positions = {date: index for index, date in enumerate(dates)}
    folds = []
    month_ends = monthly_dates(dates if calendar is None else pd.DatetimeIndex(calendar))
    for date in month_ends:
        if date not in positions:
            continue
        index = positions[date]
        if index >= minimum_train_sessions + embargo_sessions:
            folds.append(WalkForwardFold(dates[index - embargo_sessions], date, embargo_sessions))
    return folds


def training_rows(panel: pd.DataFrame, fold: WalkForwardFold) -> pd.DataFrame:
    """Rows ending before the embargo boundary; later labels are never in training."""
    return panel.loc[panel.date <= fold.train_end].copy()


def sampled_training_rows(
    panel: pd.DataFrame, train_end: pd.Timestamp, stride_sessions: int
) -> pd.DataFrame:
    """Training rows on every ``stride_sessions``-th date, counted back from ``train_end``.

    The most recent permissible date is always kept, so thinning never moves the
    embargo boundary.
    """
    if stride_sessions < 1:
        raise ValueError("Training stride must be at least one session.")
    dates = pd.DatetimeIndex(panel.date.unique()).sort_values()
    eligible = dates[dates <= train_end]
    kept = eligible[::-1][::stride_sessions]
    return panel.loc[panel.date.isin(kept)].copy()
