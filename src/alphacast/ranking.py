"""Comparable cross-sectional ranking models and diagnostics."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS, TARGET_COLUMN


def momentum_score(rows: pd.DataFrame) -> pd.Series:
    """Simple 12-1 momentum baseline: complex models must beat this fairly."""
    return rows.momentum_12_1.rank(pct=True)


def build_model(name: str, random_seed: int = 17):
    """Build a deterministic model from the approved, comparable model suite."""
    factories: dict[str, Callable[[], object]] = {
        "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "elastic_net": lambda: make_pipeline(
            StandardScaler(),
            ElasticNet(alpha=0.001, l1_ratio=0.25, max_iter=10_000, random_state=random_seed),
        ),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=40,
            min_samples_leaf=4,
            max_features=0.8,
            n_jobs=-1,
            random_state=random_seed,
        ),
    }
    if name not in factories:
        raise ValueError(f"Unsupported model '{name}'.")
    return factories[name]()


def model_score(
    name: str, train: pd.DataFrame, rows: pd.DataFrame, *, random_seed: int = 17
) -> tuple[pd.Series, pd.Series]:
    """Fit on chronological training rows and score one future cross-section."""
    if name == "momentum":
        scores = momentum_score(rows)
        return scores, pd.Series({"momentum_12_1": 1.0})
    model = build_model(name, random_seed)
    model.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])
    scores = pd.Series(model.predict(rows[FEATURE_COLUMNS]), index=rows.index, dtype=float)
    return scores, feature_importance(model)


def feature_importance(model: object) -> pd.Series:
    """Expose signed linear coefficients or tree importances in a common table."""
    estimator = model[-1] if hasattr(model, "__getitem__") else model
    if hasattr(estimator, "coef_"):
        values = np.abs(np.asarray(estimator.coef_).reshape(-1))
    elif hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_)
    else:  # pragma: no cover - guarded by the approved model suite
        values = np.zeros(len(FEATURE_COLUMNS))
    return pd.Series(values, index=FEATURE_COLUMNS, dtype=float).sort_values(ascending=False)


def rank_diagnostics(rows: pd.DataFrame, scores: pd.Series) -> dict[str, float]:
    """Evaluate rank ordering and quintile separation, never price-target accuracy."""
    if len(rows) < 10:
        raise ValueError("Need at least ten securities to evaluate a cross-sectional ranking.")
    actual = rows[TARGET_COLUMN]
    ic = scores.rank().corr(actual.rank(), method="spearman")
    ranked = rows.assign(score=scores).sort_values("score", ascending=False)
    group = max(1, len(ranked) // 5)
    q1 = ranked.head(group)[TARGET_COLUMN].mean()
    q5 = ranked.tail(group)[TARGET_COLUMN].mean()
    return {
        "rank_ic": float(ic),
        "q1_return": float(q1),
        "q5_return": float(q5),
        "q1_q5_spread": float(q1 - q5),
        "securities": float(len(rows)),
    }
