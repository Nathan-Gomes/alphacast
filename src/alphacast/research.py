"""End-to-end, embargoed cross-sectional research and portfolio accounting."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import SUPPORTED_MODELS, ResearchConfig
from .contracts import DataQualityReport, StudyResult
from .data import synthetic_prices, validate_price_panel
from .features import build_panel, research_ready
from .portfolio import top_ranked_portfolio
from .ranking import model_score, rank_diagnostics
from .validation import expanding_folds, training_rows


@dataclass(frozen=True)
class ResearchRun:
    """Artifacts produced by one declared data/configuration/model run."""

    source: str
    quality: DataQualityReport
    config: ResearchConfig
    summaries: pd.DataFrame
    periods: pd.DataFrame
    latest_rankings: pd.DataFrame
    feature_importance: pd.DataFrame
    regimes: pd.DataFrame
    monitoring: pd.DataFrame

    def to_dict(self) -> dict[str, object]:
        """Return JSON-friendly report data for the API and static exports."""
        return {
            "source": self.source,
            "quality": self.quality.to_dict(),
            "config": self.config.to_dict(),
            "summaries": _records(self.summaries),
            "periods": _records(self.periods),
            "latest_rankings": _records(self.latest_rankings),
            "feature_importance": _records(self.feature_importance),
            "regimes": _records(self.regimes),
            "monitoring": _records(self.monitoring),
            "limits": [
                "This is historical, walk-forward research; it is not an investment recommendation.",
                "Yahoo Finance data is convenient but not a point-in-time institutional data source.",
                "The starter universe is manually declared and can carry selection and survivorship bias.",
                "Portfolio results use a transparent equal-weight top-ranked sleeve, not an execution model.",
            ],
        }


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    result = frame.copy()
    for column in result.select_dtypes(include=["datetime", "datetimetz"]).columns:
        result[column] = result[column].dt.strftime("%Y-%m-%d")
    return result.replace({np.nan: None}).to_dict(orient="records")


def _summary(model: str, periods: pd.DataFrame) -> dict[str, object]:
    net = periods.net_return
    benchmark = periods.benchmark_return
    net_volatility = float(net.std(ddof=1))
    benchmark_volatility = float(benchmark.std(ddof=1))
    return {
        "model": model,
        "folds": len(periods),
        "mean_rank_ic": float(periods.rank_ic.mean()),
        "ic_volatility": float(periods.rank_ic.std(ddof=1)),
        "ic_information_ratio": float(
            periods.rank_ic.mean() / periods.rank_ic.std(ddof=1)
            if periods.rank_ic.std(ddof=1) > 0
            else 0.0
        ),
        "positive_ic_rate": float((periods.rank_ic > 0).mean()),
        "mean_q1_q5_spread": float(periods.q1_q5_spread.mean()),
        "mean_gross_return": float(periods.gross_return.mean()),
        "mean_net_return": float(net.mean()),
        "mean_benchmark_return": float(benchmark.mean()),
        "net_sharpe": float(np.sqrt(12) * net.mean() / net_volatility if net_volatility > 0 else 0.0),
        "benchmark_sharpe": float(
            np.sqrt(12) * benchmark.mean() / benchmark_volatility if benchmark_volatility > 0 else 0.0
        ),
        "mean_turnover": float(periods.turnover.mean()),
        "annualized_cost_drag": float(periods.transaction_cost.mean() * 12),
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
            mean_q1_q5_spread=("q1_q5_spread", "mean"),
            mean_net_return=("net_return", "mean"),
        )
        .sort_values(["model", "regime"])
    )


def _monitoring_summary(periods: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    """Report recent ranking quality against the full historical sample for each model."""
    rows: list[dict[str, object]] = []
    for model, model_periods in periods.groupby("model", sort=False):
        ordered = model_periods.sort_values("date")
        recent = ordered.tail(window)
        rows.append(
            {
                "model": model,
                "latest_date": ordered.date.iloc[-1],
                "window_folds": len(recent),
                "recent_mean_rank_ic": float(recent.rank_ic.mean()),
                "historical_mean_rank_ic": float(ordered.rank_ic.mean()),
                "rank_ic_change": float(recent.rank_ic.mean() - ordered.rank_ic.mean()),
                "recent_positive_ic_rate": float((recent.rank_ic > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def run_research(prices: pd.DataFrame, *, source: str, config: ResearchConfig) -> ResearchRun:
    """Run every requested model under identical chronological research rules."""
    unknown = set(config.models) - set(SUPPORTED_MODELS)
    if unknown:
        raise ValueError(f"Unsupported models: {', '.join(sorted(unknown))}")
    quality = validate_price_panel(prices, source=source)
    panel = research_ready(build_panel(prices, config.horizon_sessions))
    folds = expanding_folds(
        panel,
        minimum_train_sessions=config.minimum_train_sessions,
        embargo_sessions=config.embargo_sessions,
    )
    all_periods: list[dict[str, object]] = []
    all_rankings: list[pd.DataFrame] = []
    all_importance: list[dict[str, object]] = []

    for model_name in config.models:
        previous_weights: pd.Series | None = None
        model_periods: list[dict[str, object]] = []
        latest_ranked: pd.DataFrame | None = None
        importance_by_fold: list[pd.Series] = []
        for fold in folds:
            train = training_rows(panel, fold)
            test = panel.loc[panel.date == fold.test_date].copy()
            market_history = train.loc[:, ["date", "market_volatility_20"]].drop_duplicates("date")
            volatility_cutoff = market_history.market_volatility_20.median()
            market_return = float(test.market_return_63.iloc[0])
            market_volatility = float(test.market_volatility_20.iloc[0])
            direction = "Expansion" if market_return >= 0 else "Contraction"
            volatility = "high volatility" if market_volatility > volatility_cutoff else "low volatility"
            scores, importance = model_score(
                model_name, train, test, random_seed=config.random_seed
            )
            diagnostics = rank_diagnostics(test, scores)
            portfolio, previous_weights = top_ranked_portfolio(
                test,
                scores,
                previous_weights,
                top_n=config.top_n,
                transaction_cost_bps=config.transaction_cost_bps,
            )
            row = {
                "model": model_name,
                "date": fold.test_date,
                **diagnostics,
                "gross_return": portfolio.gross_return,
                "net_return": portfolio.net_return,
                "benchmark_return": portfolio.benchmark_return,
                "turnover": portfolio.turnover,
                "transaction_cost": portfolio.transaction_cost,
                "market_return_63": market_return,
                "market_volatility_20": market_volatility,
                "regime": f"{direction} / {volatility}",
            }
            model_periods.append(row)
            importance_by_fold.append(importance)
            latest_ranked = (
                test.assign(score=scores)
                .sort_values("score", ascending=False)
                .loc[:, ["date", "ticker", "sector", "score", "momentum_12_1", "volatility_20"]]
                .assign(model=model_name)
            )
        periods = pd.DataFrame(model_periods)
        if periods.empty:
            raise RuntimeError("The research run did not create an out-of-sample fold.")
        all_periods.extend(model_periods)
        if latest_ranked is not None:
            latest_ranked["rank"] = range(1, len(latest_ranked) + 1)
            all_rankings.append(latest_ranked)
        average_importance = pd.concat(importance_by_fold, axis=1).fillna(0.0).mean(axis=1)
        all_importance.extend(
            {
                "model": model_name,
                "feature": feature,
                "importance": float(value),
            }
            for feature, value in average_importance.sort_values(ascending=False).items()
        )

    period_frame = pd.DataFrame(all_periods).sort_values(["model", "date"])
    summaries = pd.DataFrame(
        [_summary(model, group) for model, group in period_frame.groupby("model", sort=False)]
    ).sort_values("mean_rank_ic", ascending=False)
    regimes = _regime_summary(period_frame)
    monitoring = _monitoring_summary(period_frame)
    return ResearchRun(
        source=source,
        quality=quality,
        config=config,
        summaries=summaries.reset_index(drop=True),
        periods=period_frame.reset_index(drop=True),
        latest_rankings=pd.concat(all_rankings, ignore_index=True),
        feature_importance=pd.DataFrame(all_importance).sort_values(
            ["model", "importance"], ascending=[True, False]
        ),
        regimes=regimes.reset_index(drop=True),
        monitoring=monitoring.reset_index(drop=True),
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
