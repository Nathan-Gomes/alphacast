"""Comparable cross-sectional ranking models, attribution, and diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS, TARGET_COLUMN, cross_sectional_ranks


def momentum_score(rows: pd.DataFrame) -> pd.Series:
    """Simple 12-1 momentum baseline: complex models must beat this fairly."""
    return rows.momentum_12_1.rank(pct=True)


def build_model(name: str, random_seed: int = 17):
    """Build a deterministic model from the declared, comparable model suite."""
    factories: dict[str, Callable[[], object]] = {
        "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "elastic_net": lambda: make_pipeline(
            StandardScaler(),
            ElasticNet(alpha=0.0005, l1_ratio=0.5, max_iter=10_000, random_state=random_seed),
        ),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=80,
            max_depth=6,
            min_samples_leaf=100,
            max_features=0.5,
            max_samples=0.5,
            n_jobs=-1,
            random_state=random_seed,
        ),
        "gradient_boosting": lambda: HistGradientBoostingRegressor(
            max_iter=150,
            learning_rate=0.05,
            max_leaf_nodes=15,
            min_samples_leaf=200,
            l2_regularization=1.0,
            random_state=random_seed,
        ),
    }
    if name not in factories:
        raise ValueError(f"Unsupported model '{name}'.")
    return factories[name]()


def training_target(train: pd.DataFrame) -> pd.Series:
    """Winsorize each date's labels at its 2.5th/97.5th percentile before fitting.

    One takeover or earnings gap can dominate a squared-error fit. Clipping applies to
    training labels only; every evaluation uses the unclipped realised outcome.
    """
    target = train[TARGET_COLUMN]
    by_date = target.groupby(train.date)
    return target.clip(by_date.transform("quantile", 0.025), by_date.transform("quantile", 0.975))


@dataclass
class FittedRanker:
    """A model fitted on one training window, able to score and explain a cross-section."""

    name: str
    estimator: object | None

    def score(self, rows: pd.DataFrame) -> pd.Series:
        if self.estimator is None:
            return momentum_score(rows)
        values = self.estimator.predict(cross_sectional_ranks(rows).to_numpy())
        return pd.Series(values, index=rows.index, dtype=float)

    def attribution(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Occlusion attribution: score change when a feature is set to the date median.

        For a linear model this is exactly coefficient x centred rank. For the tree
        models it is a local, model-agnostic approximation, and it ignores interactions.
        """
        if self.estimator is None:
            contributions = pd.DataFrame(0.0, index=rows.index, columns=FEATURE_COLUMNS)
            contributions["momentum_12_1"] = momentum_score(rows) - 0.5
            return contributions
        matrix = cross_sectional_ranks(rows).to_numpy()
        base = self.estimator.predict(matrix)
        contributions = np.empty_like(matrix)
        for column in range(matrix.shape[1]):
            occluded = matrix.copy()
            occluded[:, column] = 0.0
            contributions[:, column] = base - self.estimator.predict(occluded)
        return pd.DataFrame(contributions, index=rows.index, columns=FEATURE_COLUMNS)


def fit_ranker(name: str, train: pd.DataFrame, *, random_seed: int = 17) -> FittedRanker:
    """Fit on chronological training rows. The momentum baseline has nothing to fit."""
    if name == "momentum":
        return FittedRanker(name, None)
    model = build_model(name, random_seed)
    model.fit(cross_sectional_ranks(train).to_numpy(), training_target(train).to_numpy())
    return FittedRanker(name, model)


def importance_from_attribution(contributions: pd.DataFrame) -> pd.Series:
    """Share of mean absolute attribution per feature, so models are on one scale."""
    magnitude = contributions.abs().mean()
    total = magnitude.sum()
    shares = magnitude / total if total > 0 else magnitude
    return shares.reindex(FEATURE_COLUMNS).fillna(0.0)


def model_score(
    name: str, train: pd.DataFrame, rows: pd.DataFrame, *, random_seed: int = 17
) -> tuple[pd.Series, pd.Series]:
    """Fit on training rows, score one future cross-section, and report reliance."""
    ranker = fit_ranker(name, train, random_seed=random_seed)
    return ranker.score(rows), importance_from_attribution(ranker.attribution(rows))


def quintile_labels(scores: pd.Series) -> pd.Series:
    """Q1 is the highest-scored fifth. Ties are broken by order to keep groups even."""
    order = scores.rank(method="first", ascending=False)
    return np.ceil(order / len(scores) * 5).clip(1, 5).astype(int)


def rank_diagnostics(rows: pd.DataFrame, scores: pd.Series) -> dict[str, float]:
    """Evaluate rank ordering and quintile separation, never price-target accuracy."""
    if len(rows) < 10:
        raise ValueError("Need at least ten securities to evaluate a cross-sectional ranking.")
    actual = rows[TARGET_COLUMN]
    ic = scores.rank().corr(actual.rank())
    quintiles = actual.groupby(quintile_labels(scores)).mean().reindex(range(1, 6))
    return {
        "rank_ic": float(0.0 if np.isnan(ic) else ic),
        **{f"q{group}_return": float(quintiles[group]) for group in range(1, 6)},
        "q1_q5_spread": float(quintiles[1] - quintiles[5]),
        "securities": float(len(rows)),
    }
