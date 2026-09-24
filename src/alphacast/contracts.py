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


@dataclass(frozen=True)
class DataQualityReport:
    """Coverage checks for an input price panel."""

    source: str
    requested_tickers: int
    accepted_tickers: int
    sessions: int
    first_date: pd.Timestamp
    last_date: pd.Timestamp
    missing_observations: int
    dropped_sessions: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "requested_tickers": self.requested_tickers,
            "accepted_tickers": self.accepted_tickers,
            "sessions": self.sessions,
            "first_date": self.first_date.date().isoformat(),
            "last_date": self.last_date.date().isoformat(),
            "missing_observations": self.missing_observations,
            "dropped_sessions": self.dropped_sessions,
        }


def monthly_dates(dates: pd.DatetimeIndex) -> Iterator[pd.Timestamp]:
    """The final available session of each calendar month in ``dates``."""
    unique = pd.DatetimeIndex(dates.unique()).sort_values()
    for _, group in pd.Series(unique, index=unique).groupby(unique.to_period("M")):
        yield group.iloc[-1]
