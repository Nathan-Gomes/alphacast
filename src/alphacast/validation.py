"""Chronological folds with an embargo for overlapping forward labels."""

from __future__ import annotations

import pandas as pd

from .contracts import WalkForwardFold, monthly_dates


def expanding_folds(
    panel: pd.DataFrame,
    minimum_train_sessions: int = 252,
    embargo_sessions: int = 20,
) -> list[WalkForwardFold]:
    dates = pd.DatetimeIndex(panel.date.unique()).sort_values()
    if len(dates) <= minimum_train_sessions + embargo_sessions:
        raise ValueError("Not enough completed history for an expanding, embargoed study.")
    positions = {date: index for index, date in enumerate(dates)}
    folds = []
    for date in monthly_dates(dates):
        index = positions[date]
        if index >= minimum_train_sessions + embargo_sessions:
            folds.append(WalkForwardFold(dates[index - embargo_sessions], date, embargo_sessions))
    return folds


def training_rows(panel: pd.DataFrame, fold: WalkForwardFold) -> pd.DataFrame:
    """Rows ending before the embargo boundary; later labels are never in training."""
    return panel.loc[panel.date <= fold.train_end].copy()
