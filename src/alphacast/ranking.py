"""Cross-sectional model scores and ranking diagnostics."""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS, TARGET_COLUMN


def momentum_score(rows: pd.DataFrame) -> pd.Series:
    return rows.momentum_12_1.rank(pct=True)


def ridge_score(train: pd.DataFrame, rows: pd.DataFrame, alpha: float = 10.0) -> pd.Series:
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])
    return pd.Series(model.predict(rows[FEATURE_COLUMNS]), index=rows.index)


def rank_diagnostics(rows: pd.DataFrame, scores: pd.Series) -> dict[str, float]:
    if len(rows) < 10:
        raise ValueError("Need at least ten securities to evaluate a cross-sectional ranking.")
    actual = rows[TARGET_COLUMN]
    ic = scores.rank().corr(actual.rank(), method="spearman")
    ranked = rows.assign(score=scores).sort_values("score", ascending=False)
    group = max(1, len(ranked) // 5)
    spread = ranked.head(group)[TARGET_COLUMN].mean() - ranked.tail(group)[TARGET_COLUMN].mean()
    return {"rank_ic": float(ic), "q1_q5_spread": float(spread), "securities": float(len(rows))}
