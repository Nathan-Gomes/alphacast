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
from .diagnostics import (
    add_significance,
    feature_drift,
    model_summary,
    monitoring_summary,
    regime_summary,
    sector_summary,
    signal_decay,
)
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
    book_sizes: pd.DataFrame = field(default_factory=pd.DataFrame)

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
            "book_sizes": _records(self.book_sizes),
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


def trailing_betas(panel: pd.DataFrame, sessions: int = 252) -> pd.Series:
    """Each stock's beta to the equal-weight universe over the last ``sessions`` days.

    Descriptive only: it explains the portfolio's market exposure and is not a model
    input.
    """
    returns = panel.pivot(index="date", columns="ticker", values="adjusted_close").pct_change()
    recent = returns.iloc[-sessions:]
    market = recent.mean(axis=1)
    variance = market.var(ddof=1)
    if not variance or np.isnan(variance):
        return pd.Series(dtype=float)
    return recent.apply(lambda column: column.cov(market) / variance)


def neutralize(scores: pd.Series, exposure: pd.Series) -> pd.Series:
    """Remove the part of today's scores explained by a stock's volatility rank.

    The residual keeps the model's ordering within similar-risk stocks, so the sleeve
    cannot earn its return simply by holding the most volatile names.
    """
    centred = exposure.rank(pct=True).to_numpy() - 0.5
    design = np.column_stack([np.ones(len(centred)), centred])
    coef, *_ = np.linalg.lstsq(design, scores.to_numpy(), rcond=None)
    return pd.Series(scores.to_numpy() - centred * coef[1], index=scores.index)


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


BOOK_SIZES = (5, 10, 15, 20, 30)


def book_size_sweep(
    folds: list,
    fold_outputs: dict[str, list[tuple[pd.Series, pd.Series, pd.Timestamp]]],
    test_rows: dict[pd.Timestamp, pd.DataFrame],
    config: ResearchConfig,
) -> pd.DataFrame:
    """Rebuild each model's sleeve at other book sizes from the same fold scores.

    Nothing is refitted: only the number of names changes. Cadence, costs and the sector
    cap are kept; a holding buffer keeps its ratio to the book size. It answers whether
    the result depends on choosing exactly ``top_n`` names.
    """
    breadth = min(len(test_rows[fold.test_date]) for fold in folds)
    sizes = sorted({size for size in (*BOOK_SIZES, config.top_n) if size <= breadth // 2})
    rows: list[dict[str, object]] = []
    for model_name, outputs in fold_outputs.items():
        for size in sizes:
            buffer = (
                max(size + 1, round(config.hold_buffer * size / config.top_n))
                if config.hold_buffer
                else None
            )
            weights: pd.Series | None = None
            net, benchmark, turnover = [], [], []
            for fold_index, (fold, (scores, _, _)) in enumerate(zip(folds, outputs)):
                test = test_rows[fold.test_date]
                if weights is not None and fold_index % max(config.rebalance_every_folds, 1):
                    step = hold_portfolio(test, weights)
                else:
                    step, weights = top_ranked_portfolio(
                        test, scores, weights, top_n=size,
                        transaction_cost_bps=config.transaction_cost_bps,
                        max_per_sector=config.max_per_sector, hold_buffer=buffer,
                    )
                net.append(step.net_return)
                benchmark.append(step.benchmark_return)
                turnover.append(step.turnover)
            net_series, bench_series = pd.Series(net), pd.Series(benchmark)
            years = len(net) / 12
            annualized = float((1 + net_series).prod() ** (1 / years) - 1)
            annualized_benchmark = float((1 + bench_series).prod() ** (1 / years) - 1)
            deviation = float(net_series.std(ddof=1))
            rows.append(
                {
                    "model": model_name,
                    "top_n": size,
                    "net_sharpe": float(np.sqrt(12) * net_series.mean() / deviation) if deviation else 0.0,
                    "annualized_net_return": annualized,
                    "annualized_active_return": annualized - annualized_benchmark,
                    "mean_turnover": float(np.mean(turnover)),
                }
            )
    return pd.DataFrame(rows)


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
            scores = ranker.score(test)
            if config.neutralize_volatility:
                scores = neutralize(scores, test.volatility_60)
            outputs.append(
                (scores, importance_from_attribution(ranker.attribution(test)), fitted_through)
            )
            completed += 1
            report(0.05 + 0.9 * completed / steps, f"{label}: fold {fold.test_date.date().isoformat()}")
        fold_outputs[model_name] = outputs
        # Live signal: fit on every label already realised at the latest close. No
        # embargo is needed because the live cross-section has no known label yet.
        report(0.05 + 0.9 * completed / steps, f"{label}: scoring {signal_date.date().isoformat()}")
        ranker = fit_ranker(model_name, sampler.rows(live_train_end), random_seed=config.random_seed)
        live_scores = ranker.score(live_rows)
        if config.neutralize_volatility:
            live_scores = neutralize(live_scores, live_rows.volatility_60)
        live_outputs[model_name] = (live_scores, ranker.attribution(live_rows))
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
                    hold_buffer=config.hold_buffer,
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
            live_rows, live_scores, top_n=config.top_n, max_per_sector=config.max_per_sector,
            keep=set(previous_weights.index) if previous_weights is not None else None,
            keep_within=config.hold_buffer,
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
        [model_summary(model, group) for model, group in period_frame.groupby("model", sort=False)]
    )
    summaries["label"] = summaries.model.map(MODEL_LABELS)
    summaries = add_significance(summaries)
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
    profiles["beta_252"] = profiles.ticker.map(trailing_betas(full_panel))

    return ResearchRun(
        source=source,
        dataset=dataset or source,
        quality=quality,
        config=config,
        summaries=summaries,
        periods=period_frame,
        feature_importance=average_importance.reset_index(drop=True),
        importance_history=importance_history,
        regimes=regime_summary(period_frame).reset_index(drop=True),
        monitoring=monitoring_summary(period_frame, config.monitoring_window),
        live=pd.concat(live_frames, ignore_index=True),
        profiles=profiles,
        drift=feature_drift(full_panel).reset_index(drop=True),
        decay=signal_decay(full_panel, history_frame),
        sectors=sector_summary(
            history_frame, live_rows.set_index("ticker").sector
        ).reset_index(drop=True),
        history=history_frame,
        attribution=pd.concat(attribution_frames, ignore_index=True),
        weekly_prices=_weekly_prices(prices),
        signal_date=signal_date,
        last_rebalance=folds[-1].test_date,
        book_sizes=book_size_sweep(folds, fold_outputs, test_rows, config),
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
