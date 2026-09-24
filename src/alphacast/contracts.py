"""Small, explicit contracts shared by the research layers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    """One expanding training window and one future scoring date."""

    train_end: pd.Timestamp
    test_date: pd.Timestamp
    embargo_sessions: int


@dataclass(frozen=True)
class StudyResult:
    """Out-of-sample diagnostics for one model; not a trading recommendation."""

    model: str
    observations: int
    mean_rank_ic: float
    positive_ic_rate: float
    mean_q1_q5_spread: float
    monthly: pd.DataFrame


def monthly_dates(dates: pd.DatetimeIndex) -> Iterator[pd.Timestamp]:
    """The final available session of each calendar month."""
    unique = pd.DatetimeIndex(dates.unique()).sort_values()
    for _, group in pd.Series(unique, index=unique).groupby(unique.to_period("M")):
        yield group.iloc[-1]
