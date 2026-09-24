"""The first end-to-end, walk-forward research run."""

from __future__ import annotations

import pandas as pd

from .contracts import StudyResult
from .data import synthetic_prices
from .features import build_panel, research_ready
from .ranking import momentum_score, rank_diagnostics, ridge_score
from .validation import expanding_folds, training_rows


def run_study(model: str = "ridge") -> StudyResult:
    panel = research_ready(build_panel(synthetic_prices()))
    outcomes = []
    for fold in expanding_folds(panel):
        train = training_rows(panel, fold)
        test = panel.loc[panel.date == fold.test_date].copy()
        scores = momentum_score(test) if model == "momentum" else ridge_score(train, test)
        outcomes.append({"date": fold.test_date, **rank_diagnostics(test, scores)})
    monthly = pd.DataFrame(outcomes)
    if monthly.empty:
        raise RuntimeError("The study did not create an out-of-sample fold.")
    return StudyResult(
        model=model,
        observations=len(monthly),
        mean_rank_ic=float(monthly.rank_ic.mean()),
        positive_ic_rate=float((monthly.rank_ic > 0).mean()),
        mean_q1_q5_spread=float(monthly.q1_q5_spread.mean()),
        monthly=monthly,
    )
