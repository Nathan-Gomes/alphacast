"""End-to-end, embargoed cross-sectional research, live scoring, and portfolio accounting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import MODEL_LABELS, SUPPORTED_MODELS, ResearchConfig
from .contracts import DataQualityReport, StudyResult
from .data import drop_incomplete_sessions, synthetic_prices, validate_price_panel
from .features import (
    FEATURE_COLUMNS,
    FEATURE_LABELS,
    TARGET_COLUMN,
    build_panel,
    factor_percentiles,
    latest_cross_section,
    research_ready,
    with_cross_sectional_ranks,
)
from .portfolio import hold_portfolio, select_top, top_ranked_portfolio
from .ranking import (
    fit_ranker,
    importance_from_attribution,
    quintile_labels,
    rank_diagnostics,
    training_target,
)
from .validation import TrainingSampler, expanding_folds

Progress = Callable[[float, str], None]

LIMITS = [
    "Historical walk-forward research. Nothing here is an investment recommendation.",
    "Yahoo Finance history is convenient, not a point-in-time institutional data source.",
    (
        "Universes are today's constituents written down by hand, so results carry "
        "survivorship bias."
    ),
    "No fundamentals, delisting returns, borrow costs, taxes, or spread and impact model.",
    "The portfolio is an equal-weight top-ranked sleeve, not an optimizer or execution model.",
]


@dataclass
class ResearchRun:
    """Artifacts produced by one declared data/configuration/model run."""

    source: str
    dataset: str
    quality: DataQualityReport
    config: ResearchConfig
    summaries: pd.DataFrame
    periods: pd.DataFrame
    feature_importance: pd.DataFrame
    importance_history: pd.DataFrame
    regimes: pd.DataFrame
    monitoring: pd.DataFrame
    live: pd.DataFrame
    profiles: pd.DataFrame
    drift: pd.DataFrame
    sectors: pd.DataFrame
    decay: pd.DataFrame
    history: pd.DataFrame
    attribution: pd.DataFrame
    weekly_prices: pd.DataFrame
    signal_date: pd.Timestamp
    last_rebalance: pd.Timestamp
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def latest_rankings(self) -> pd.DataFrame:
        """The live cross-section, kept under the name the original API used."""
        return self.live

    def to_dict(self) -> dict[str, object]:
        """The workspace payload: everything the interface needs except per-security detail."""
        return {
            "created_at": self.created_at,
            "source": self.source,
            "dataset": self.dataset,
            "quality": self.quality.to_dict(),
            "config": self.config.to_dict(),
            "signal_date": _day(self.signal_date),
            "last_rebalance": _day(self.last_rebalance),
            "models": [
                {"id": model, "label": MODEL_LABELS[model]} for model in self.summaries.model
            ],
            "features": [
                {"id": feature, "label": FEATURE_LABELS[feature]} for feature in FEATURE_COLUMNS
            ],
            "summaries": _records(self.summaries),
            "periods": _records(self.periods),
            "feature_importance": _records(self.feature_importance),
            "importance_history": _importance_matrix(self.importance_history),
            "regimes": _records(self.regimes),
            "monitoring": _records(self.monitoring),
            "live": _records(self.live),
            "profiles": _records(self.profiles),
            "drift": _records(self.drift),
            "sectors": _records(self.sectors),
            "decay": _records(self.decay),
            "limits": LIMITS,
        }

    def security_details(self) -> dict[str, dict[str, object]]:
        """Per-security detail served on demand: price path, rank history, attribution."""
        details: dict[str, dict[str, object]] = {}
        prices = self.weekly_prices.groupby("ticker")
        history = self.history.groupby("ticker")
        attribution = self.attribution.groupby("ticker")
        for profile in _records(self.profiles):
            ticker = profile["ticker"]
            weekly = prices.get_group(ticker) if ticker in prices.groups else pd.DataFrame()
            details[ticker] = {
                "profile": profile,
                "prices": {
                    "dates": [_day(value) for value in weekly.get("date", [])],
                    "close": [round(float(value), 4) for value in weekly.get("adjusted_close", [])],
                },
                "history": {
                    model: _records(group.drop(columns=["ticker", "model"]))
                    for model, group in history.get_group(ticker).groupby("model", sort=False)
                }
                if ticker in history.groups
                else {},
                "attribution": {
                    model: _records(group.drop(columns=["ticker", "model"]))
                    for model, group in attribution.get_group(ticker).groupby("model", sort=False)
                }
                if ticker in attribution.groups
                else {},
            }
        return details


def _day(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    result = frame.copy()
    for column in result.select_dtypes(include=["datetime", "datetimetz"]).columns:
        result[column] = result[column].dt.strftime("%Y-%m-%d")
    for column in result.select_dtypes(include=["float"]).columns:
        result[column] = result[column].round(6)
    result = result.astype(object).where(result.notna(), None)
    return result.to_dict(orient="records")


def _importance_matrix(history: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Per-model fold x feature matrix; far smaller than long-form records."""
    matrices: dict[str, dict[str, object]] = {}
    for model, group in history.groupby("model", sort=False):
        wide = group.pivot(index="date", columns="feature", values="importance")
        wide = wide.reindex(columns=FEATURE_COLUMNS).fillna(0.0).sort_index()
        matrices[model] = {
            "dates": [_day(value) for value in wide.index],
            "values": np.round(wide.to_numpy(), 4).tolist(),
        }
    return matrices


def _max_drawdown(returns: pd.Series) -> float:
    wealth = (1 + returns).cumprod()
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth.to_numpy()]))[1:]
    return float((wealth / peak - 1).min()) if len(wealth) else 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else 0.0


def _summary(model: str, periods: pd.DataFrame) -> dict[str, object]:
    net = periods.net_return
    gross = periods.gross_return
    benchmark = periods.benchmark_return
    active = net - benchmark
    ic = periods.rank_ic
    years = len(periods) / 12
    return {
        "model": model,
        "folds": len(periods),
        "mean_rank_ic": float(ic.mean()),
        "ic_volatility": float(ic.std(ddof=1)),
        "ic_information_ratio": _ratio(ic.mean(), ic.std(ddof=1)),
        "ic_t_stat": _ratio(ic.mean(), ic.std(ddof=1) / np.sqrt(len(ic))),
        "positive_ic_rate": float((ic > 0).mean()),
        "mean_q1_q5_spread": float(periods.q1_q5_spread.mean()),
        "monotonic_rate": float(
            (periods[[f"q{group}_return" for group in range(1, 6)]].diff(axis=1).iloc[:, 1:] < 0)
            .all(axis=1)
            .mean()
        ),
        "mean_gross_return": float(gross.mean()),
        "mean_net_return": float(net.mean()),
        "mean_benchmark_return": float(benchmark.mean()),
        "annualized_net_return": float((1 + net).prod() ** (1 / years) - 1) if years else 0.0,
        "annualized_benchmark_return": float((1 + benchmark).prod() ** (1 / years) - 1)
        if years
        else 0.0,
        "annualized_volatility": float(net.std(ddof=1) * np.sqrt(12)),
        "gross_sharpe": _ratio(np.sqrt(12) * gross.mean(), gross.std(ddof=1)),
        "net_sharpe": _ratio(np.sqrt(12) * net.mean(), net.std(ddof=1)),
        "benchmark_sharpe": _ratio(np.sqrt(12) * benchmark.mean(), benchmark.std(ddof=1)),
        "information_ratio": _ratio(np.sqrt(12) * active.mean(), active.std(ddof=1)),
        "hit_rate": float((active > 0).mean()),
        "max_drawdown": _max_drawdown(net),
        "benchmark_max_drawdown": _max_drawdown(benchmark),
        "mean_turnover": float(periods.turnover.mean()),
        "annualized_cost_drag": float(periods.transaction_cost.mean() * 12),
        "gross_terminal_growth": float((1 + gross).prod() - 1),
        "net_terminal_growth": float((1 + net).prod() - 1),
        "benchmark_terminal_growth": float((1 + benchmark).prod() - 1),
    }


def _regime_summary(periods: pd.DataFrame) -> pd.DataFrame:
    """Summarize out-of-sample diagnostics by a regime defined before each test date."""
    return (
        periods.groupby(["model", "regime"], as_index=False)
        .agg(
            folds=("date", "size"),
            mean_rank_ic=("rank_ic", "mean"),
            positive_ic_rate=("rank_ic", lambda values: float((values > 0).mean())),
            mean_q1_q5_spread=("q1_q5_spread", "mean"),
            mean_net_return=("net_return", "mean"),
            mean_benchmark_return=("benchmark_return", "mean"),
        )
        .sort_values(["model", "regime"])
    )


def _monitoring_summary(periods: pd.DataFrame, window: int) -> pd.DataFrame:
    """Compare recent ranking quality with the full sample and assign a declared status.

    ``degraded``: the recent mean Rank IC is negative.
    ``watch``: it sits more than one standard error below the full-sample mean.
    ``healthy``: neither.
    """
    rows: list[dict[str, object]] = []
    for model, model_periods in periods.groupby("model", sort=False):
        ordered = model_periods.sort_values("date")
        recent = ordered.tail(window)
        historical = float(ordered.rank_ic.mean())
        recent_ic = float(recent.rank_ic.mean())
        standard_error = float(ordered.rank_ic.std(ddof=1) / np.sqrt(max(len(recent), 1)))
        if recent_ic < 0:
            status = "degraded"
        elif recent_ic < historical - standard_error:
            status = "watch"
        else:
            status = "healthy"
        rows.append(
            {
                "model": model,
                "status": status,
                "latest_date": ordered.date.iloc[-1],
                "window_folds": len(recent),
                "recent_mean_rank_ic": recent_ic,
                "historical_mean_rank_ic": historical,
                "rank_ic_change": recent_ic - historical,
                "standard_error": standard_error,
                "recent_positive_ic_rate": float((recent.rank_ic > 0).mean()),
                "recent_q1_q5_spread": float(recent.q1_q5_spread.mean()),
                "recent_turnover": float(recent.turnover.mean()),
            }
        )
    return pd.DataFrame(rows)


def _population_stability(reference: pd.Series, recent: pd.Series, bins: int = 10) -> float:
    """PSI of ``recent`` against decile bins cut from ``reference``."""
    edges = np.unique(np.quantile(reference.dropna(), np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    expected = np.histogram(reference.dropna(), edges)[0] / reference.notna().sum()
    actual = np.histogram(recent.dropna(), edges)[0] / max(recent.notna().sum(), 1)
    expected = np.clip(expected, 1e-4, None)
    actual = np.clip(actual, 1e-4, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def _feature_drift(panel: pd.DataFrame, recent_sessions: int = 63) -> pd.DataFrame:
    """Raw feature distributions over the last quarter compared with all prior history.

    Models see within-date ranks, so a drifting raw level does not reach them directly.
    Drift still matters: it says today's market looks unlike most training data.
    """
    complete = panel.dropna(subset=FEATURE_COLUMNS)
    dates = pd.DatetimeIndex(complete.date.unique()).sort_values()
    cutoff = dates[-min(recent_sessions, len(dates))]
    reference = complete.loc[complete.date < cutoff]
    recent = complete.loc[complete.date >= cutoff]
    rows = []
    for feature in FEATURE_COLUMNS:
        psi = _population_stability(reference[feature], recent[feature])
        spread = reference[feature].std(ddof=1)
        rows.append(
            {
                "feature": feature,
                "psi": psi,
                "reference_median": float(reference[feature].median()),
                "recent_median": float(recent[feature].median()),
                "median_shift_sd": _ratio(
                    recent[feature].median() - reference[feature].median(), spread
                )
                if spread > 0
                else 0.0,
                "status": "shifted" if psi >= 0.25 else "moderate" if psi >= 0.1 else "stable",
            }
        )
    return pd.DataFrame(rows).sort_values("psi", ascending=False)


def _sector_summary(history: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
    """Where each model's ranking works, and where its portfolio leans, by sector.

    The target is already sector-relative, so a within-sector Rank IC asks whether the
    model orders stocks correctly inside each sector. Active weight compares the
    top-ranked sleeve's sector share with the universe's, averaged over folds.
    """
    frame = history.assign(sector=history.ticker.map(sector_of))
    rows: list[dict[str, object]] = []
    for (model, sector), group in frame.groupby(["model", "sector"], sort=False):
        per_date = group.groupby("date")
        ic = per_date.apply(
            lambda rows: rows.percentile.corr(rows.realized, method="spearman")
            if len(rows) >= 4
            else np.nan,
            include_groups=False,
        ).dropna()
        held = frame.loc[frame.model == model].groupby("date")
        sleeve_share = per_date.held.sum() / held.held.sum()
        universe_share = per_date.size() / held.size()
        rows.append(
            {
                "model": model,
                "sector": sector,
                "names": int(group.ticker.nunique()),
                "folds": len(ic),
                "mean_rank_ic": float(ic.mean()) if len(ic) else np.nan,
                "positive_ic_rate": float((ic > 0).mean()) if len(ic) else np.nan,
                "mean_active_weight": float((sleeve_share - universe_share).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["model", "mean_active_weight"], ascending=[True, False])


DECAY_HORIZONS = (5, 10, 20, 40, 60)


def _forward_sector_excess(panel: pd.DataFrame, horizon: int) -> pd.Series:
    """Forward return over ``horizon`` sessions minus the sector's equal-weight mean."""
    forward = panel.groupby("ticker").adjusted_close.transform(
        lambda values: values.shift(-horizon) / values - 1
    )
    return forward - forward.groupby([panel.date, panel.sector]).transform("mean")


def _signal_decay(
    panel: pd.DataFrame, history: pd.DataFrame, horizons: tuple[int, ...] = DECAY_HORIZONS
) -> pd.DataFrame:
    """Mean Rank IC of each model's fold scores against outcomes at several horizons.

    Evaluation only: the models are trained on the 20-session target. A signal whose IC
    falls quickly past 20 sessions is short-lived; one that holds is slower-moving.
    """
    outcomes = panel.loc[:, ["date", "ticker"]].copy()
    for horizon in horizons:
        outcomes[f"h{horizon}"] = _forward_sector_excess(panel, horizon).to_numpy()
    merged = history.merge(outcomes, on=["date", "ticker"], how="left")
    rows = []
    for model, group in merged.groupby("model", sort=False):
        for horizon in horizons:
            column = f"h{horizon}"
            ic = (
                group.dropna(subset=[column])
                .groupby("date")
                .apply(
                    lambda rows, column=column: rows.percentile.corr(rows[column], method="spearman"),
                    include_groups=False,
                )
                .dropna()
            )
            rows.append(
                {
                    "model": model,
                    "horizon": horizon,
                    "folds": len(ic),
                    "mean_rank_ic": float(ic.mean()) if len(ic) else np.nan,
                    "ic_t_stat": _ratio(ic.mean(), ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 1 else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _weekly_prices(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.loc[:, ["date", "ticker", "adjusted_close"]].copy()
    frame["date"] = pd.to_datetime(frame.date)
    frame["week"] = frame.date.dt.to_period("W-FRI")
    return (
        frame.sort_values("date")
        .groupby(["ticker", "week"], as_index=False)
        .last()
        .loc[:, ["ticker", "date", "adjusted_close"]]
    )


def ensemble_scores(scores: list[pd.Series]) -> pd.Series:
    """Equal-weight average of the members' within-date rank percentiles.

    Ranks put every member on one scale, and equal weights mean nothing is fitted to
    the test folds.
    """
    return pd.concat([score.rank(pct=True) for score in scores], axis=1).mean(axis=1)


def ensemble_attribution(members: list[tuple[pd.Series, pd.DataFrame]]) -> pd.DataFrame:
    """Members' attributions in units of each member's score dispersion, averaged."""
    scaled = [
        contributions / (scores.std(ddof=0) or 1.0) for scores, contributions in members
    ]
    return sum(scaled) / len(scaled)


def run_research(
    prices: pd.DataFrame,
    *,
    source: str,
    config: ResearchConfig,
    dataset: str | None = None,
    progress: Progress | None = None,
) -> ResearchRun:
    """Run every requested model under identical chronological research rules."""
    report = progress or (lambda fraction, message: None)
    unknown = set(config.models) - set(SUPPORTED_MODELS)
    if unknown:
        raise ValueError(f"Unsupported models: {', '.join(sorted(unknown))}")
    if not config.models:
        raise ValueError("Select at least one model.")
    unavailable = tuple(prices.attrs.get("unavailable_tickers", ()))
    prices, dropped = drop_incomplete_sessions(prices)
    quality = validate_price_panel(
        prices, source=source, dropped_sessions=dropped, unavailable_tickers=unavailable
    )
    report(0.02, "Building trailing features")
    full_panel = build_panel(prices, config.horizon_sessions)
    panel = research_ready(full_panel)
    # A ranking needs a real cross-section; early dates of a custom universe can be thin.
    breadth = panel.groupby("date").ticker.transform("size")
    panel = panel.loc[breadth >= 10]
    folds = expanding_folds(
        panel,
        minimum_train_sessions=config.minimum_train_sessions,
        embargo_sessions=config.embargo_sessions,
        calendar=pd.DatetimeIndex(full_panel.date.unique()),
    )
    if not folds:
        raise RuntimeError("The research run did not create an out-of-sample fold.")
    live_rows = with_cross_sectional_ranks(latest_cross_section(full_panel))
    signal_date = live_rows.date.iloc[0]
    live_train_end = panel.date.max()
    # Ranks, clipped labels and market-volatility history depend only on their own
    # date, so they are computed once here rather than inside every fold and model.
    panel = with_cross_sectional_ranks(panel)
    panel["training_target"] = training_target(panel)
    sampler = TrainingSampler(panel, config.train_stride_sessions)
    market_volatility_by_date = panel.drop_duplicates("date").set_index("date").market_volatility_20
    test_rows = dict(tuple(panel.groupby("date")))

    periods: list[dict[str, object]] = []
    history: list[pd.DataFrame] = []
    importance_rows: list[dict[str, object]] = []
    live_frames: list[pd.DataFrame] = []
    attribution_frames: list[pd.DataFrame] = []
    steps = sum(model != "ensemble" for model in config.models) * (len(folds) + 1)
    completed = 0

    base_models = [model for model in config.models if model != "ensemble"]
    members = [model for model in base_models if model != "momentum"]
    if "ensemble" in config.models and len(members) < 2:
        raise ValueError("The ensemble needs at least two machine-learning models to combine.")

    # Phase 1: every model's fold scores and live scores. Base models are fitted; the
    # ensemble combines its members afterwards, so it adds no fitting time.
    fold_outputs: dict[str, list[tuple[pd.Series, pd.Series, pd.Timestamp]]] = {}
    live_outputs: dict[str, tuple[pd.Series, pd.DataFrame]] = {}
    for model_name in base_models:
        label = MODEL_LABELS[model_name]
        outputs = []
        ranker = None
        for index, fold in enumerate(folds):
            test = test_rows[fold.test_date]
            if ranker is None or index % max(config.refit_every_folds, 1) == 0:
                ranker = fit_ranker(
                    model_name, sampler.rows(fold.train_end), random_seed=config.random_seed
                )
                fitted_through = fold.train_end
            outputs.append(
                (ranker.score(test), importance_from_attribution(ranker.attribution(test)), fitted_through)
            )
            completed += 1
            report(0.05 + 0.9 * completed / steps, f"{label}: fold {fold.test_date.date().isoformat()}")
        fold_outputs[model_name] = outputs
        # Live signal: fit on every label already realised at the latest close. No
        # embargo is needed because the live cross-section has no known label yet.
        report(0.05 + 0.9 * completed / steps, f"{label}: scoring {signal_date.date().isoformat()}")
        ranker = fit_ranker(model_name, sampler.rows(live_train_end), random_seed=config.random_seed)
        live_outputs[model_name] = (ranker.score(live_rows), ranker.attribution(live_rows))
        completed += 1
    if "ensemble" in config.models:
        fold_outputs["ensemble"] = [
            (
                ensemble_scores([fold_outputs[m][i][0] for m in members]),
                pd.concat([fold_outputs[m][i][1] for m in members], axis=1).mean(axis=1),
                fold_outputs[members[0]][i][2],
            )
            for i in range(len(folds))
        ]
        live_outputs["ensemble"] = (
            ensemble_scores([live_outputs[m][0] for m in members]),
            ensemble_attribution([live_outputs[m] for m in members]),
        )

    # Phase 2: identical evaluation, portfolio and live book for every model.
    for model_name in config.models:
        previous_weights: pd.Series | None = None
        last_ranks: pd.Series | None = None
        for fold_index, (fold, (scores, importance, fitted_through)) in enumerate(
            zip(folds, fold_outputs[model_name])
        ):
            test = test_rows[fold.test_date]
            volatility_cutoff = market_volatility_by_date.loc[: fold.train_end].median()
            market_return = float(test.market_return_63.iloc[0])
            market_volatility = float(test.market_volatility_20.iloc[0])
            direction = "Expansion" if market_return >= 0 else "Contraction"
            volatility = "high vol" if market_volatility > volatility_cutoff else "low vol"
            diagnostics = rank_diagnostics(test, scores)
            if previous_weights is not None and fold_index % max(config.rebalance_every_folds, 1):
                step = hold_portfolio(test, previous_weights)
            else:
                step, previous_weights = top_ranked_portfolio(
                    test,
                    scores,
                    previous_weights,
                    top_n=config.top_n,
                    transaction_cost_bps=config.transaction_cost_bps,
                    max_per_sector=config.max_per_sector,
                )
            periods.append(
                {
                    "model": model_name,
                    "date": fold.test_date,
                    "train_end": fitted_through,
                    **diagnostics,
                    "gross_return": step.gross_return,
                    "net_return": step.net_return,
                    "benchmark_return": step.benchmark_return,
                    "turnover": step.turnover,
                    "transaction_cost": step.transaction_cost,
                    "market_return_63": market_return,
                    "market_volatility_20": market_volatility,
                    "regime": f"{direction} / {volatility}",
                }
            )
            ranks = scores.rank(ascending=False, method="first").astype(int)
            last_ranks = pd.Series(ranks.to_numpy(), index=test.ticker.to_numpy())
            history.append(
                pd.DataFrame(
                    {
                        "ticker": test.ticker.to_numpy(),
                        "model": model_name,
                        "date": fold.test_date,
                        "rank": ranks.to_numpy(),
                        "percentile": (scores.rank(pct=True) * 100).to_numpy(),
                        "quintile": quintile_labels(scores).to_numpy(),
                        "realized": test[TARGET_COLUMN].to_numpy(),
                        "held": test.ticker.isin(previous_weights.index).to_numpy(),
                    }
                )
            )
            importance_rows.extend(
                {"model": model_name, "date": fold.test_date, "feature": feature, "importance": value}
                for feature, value in importance.items()
            )

        live_scores, contributions = live_outputs[model_name]
        order = live_scores.rank(ascending=False, method="first").astype(int)
        chosen = select_top(
            live_rows, live_scores, top_n=config.top_n, max_per_sector=config.max_per_sector
        )
        top = live_rows.ticker.isin(chosen.ticker)
        live = pd.DataFrame(
            {
                "model": model_name,
                "ticker": live_rows.ticker.to_numpy(),
                "sector": live_rows.sector.to_numpy(),
                "score": live_scores.to_numpy(),
                "predicted_relative_return": live_scores.to_numpy()
                if model_name not in {"momentum", "ensemble"}
                else np.nan,
                "rank": order.to_numpy(),
                "percentile": (live_scores.rank(pct=True) * 100).to_numpy(),
                "quintile": quintile_labels(live_scores).to_numpy(),
                "in_portfolio": top.to_numpy(),
                "weight": np.where(top, 1.0 / top.sum(), 0.0),
            }
        )
        previous = last_ranks.reindex(live.ticker) if last_ranks is not None else None
        live["previous_rank"] = previous.to_numpy() if previous is not None else np.nan
        live["rank_change"] = live.previous_rank - live["rank"]
        live["was_held"] = live.ticker.isin(previous_weights.index) if previous_weights is not None else False
        live_frames.append(live.sort_values("rank"))
        percentiles = live_rows[FEATURE_COLUMNS].rank(pct=True) * 100
        for column in FEATURE_COLUMNS:
            attribution_frames.append(
                pd.DataFrame(
                    {
                        "ticker": live_rows.ticker.to_numpy(),
                        "model": model_name,
                        "feature": column,
                        "value": live_rows[column].to_numpy(),
                        "percentile": percentiles[column].to_numpy(),
                        "contribution": contributions[column].to_numpy(),
                    }
                )
            )

    report(0.97, "Summarising diagnostics")
    history_frame = pd.concat(history, ignore_index=True)
    period_frame = pd.DataFrame(periods).sort_values(["model", "date"]).reset_index(drop=True)
    summaries = pd.DataFrame(
        [_summary(model, group) for model, group in period_frame.groupby("model", sort=False)]
    )
    summaries["label"] = summaries.model.map(MODEL_LABELS)
    importance_history = pd.DataFrame(importance_rows)
    average_importance = (
        importance_history.groupby(["model", "feature"], as_index=False, sort=False)
        .importance.mean()
        .sort_values(["model", "importance"], ascending=[True, False])
    )
    recent_dates = importance_history.groupby("model").date.transform(
        lambda dates: dates >= sorted(dates.unique())[-min(config.monitoring_window, dates.nunique())]
    )
    recent_importance = (
        importance_history.loc[recent_dates]
        .groupby(["model", "feature"], as_index=False, sort=False)
        .importance.mean()
        .rename(columns={"importance": "recent_importance"})
    )
    average_importance = average_importance.merge(recent_importance, on=["model", "feature"])
    average_importance["label"] = average_importance.feature.map(FEATURE_LABELS)

    profiles = live_rows.loc[
        :, ["ticker", "sector", "adjusted_close", *FEATURE_COLUMNS]
    ].reset_index(drop=True)
    profiles = pd.concat(
        [profiles, factor_percentiles(live_rows).reset_index(drop=True)], axis=1
    ).rename(columns={"adjusted_close": "price"})
    one_day = (
        full_panel.sort_values("date")
        .groupby("ticker")
        .adjusted_close.apply(lambda values: values.iloc[-1] / values.iloc[-2] - 1)
    )
    profiles["return_1d"] = profiles.ticker.map(one_day)

    return ResearchRun(
        source=source,
        dataset=dataset or source,
        quality=quality,
        config=config,
        summaries=summaries,
        periods=period_frame,
        feature_importance=average_importance.reset_index(drop=True),
        importance_history=importance_history,
        regimes=_regime_summary(period_frame).reset_index(drop=True),
        monitoring=_monitoring_summary(period_frame, config.monitoring_window),
        live=pd.concat(live_frames, ignore_index=True),
        profiles=profiles,
        drift=_feature_drift(full_panel).reset_index(drop=True),
        decay=_signal_decay(full_panel, history_frame),
        sectors=_sector_summary(
            history_frame, live_rows.set_index("ticker").sector
        ).reset_index(drop=True),
        history=history_frame,
        attribution=pd.concat(attribution_frames, ignore_index=True),
        weekly_prices=_weekly_prices(prices),
        signal_date=signal_date,
        last_rebalance=folds[-1].test_date,
    )


def run_study(model: str = "ridge") -> StudyResult:
    """Preserve the compact deterministic study used by the original foundation."""
    config = ResearchConfig(models=(model,), minimum_train_sessions=252)
    run = run_research(synthetic_prices(), source="synthetic", config=config)
    summary = run.summaries.iloc[0]
    monthly = run.periods.drop(columns=["model"])
    return StudyResult(
        model=model,
        observations=int(summary.folds),
        mean_rank_ic=float(summary.mean_rank_ic),
        positive_ic_rate=float(summary.positive_ic_rate),
        mean_q1_q5_spread=float(summary.mean_q1_q5_spread),
        monthly=monthly,
    )
