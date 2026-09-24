"""Out-of-sample diagnostics computed from a finished walk-forward run.

Everything here reads fold results; nothing feeds back into model fitting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .features import FEATURE_COLUMNS


def max_drawdown(returns: pd.Series) -> float:
    wealth = (1 + returns).cumprod()
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth.to_numpy()]))[1:]
    return float((wealth / peak - 1).min()) if len(wealth) else 0.0


def ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else 0.0


def market_exposure(returns: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    """OLS of monthly returns on the benchmark: beta, annualised alpha and its t-stat.

    A sleeve with beta above one earns more than the universe in a rising market
    without any stock-picking skill; alpha is what remains after that exposure.
    """
    if len(returns) < 3 or benchmark.var(ddof=1) == 0:
        return {"beta": np.nan, "alpha_annualized": np.nan, "alpha_t_stat": 0.0}
    design = np.column_stack([np.ones(len(benchmark)), benchmark.to_numpy()])
    coef, *_ = np.linalg.lstsq(design, returns.to_numpy(), rcond=None)
    residual = returns.to_numpy() - design @ coef
    variance = residual @ residual / (len(returns) - 2)
    standard_errors = np.sqrt(np.diag(variance * np.linalg.inv(design.T @ design)))
    return {
        "beta": float(coef[1]),
        "alpha_annualized": float(coef[0] * 12),
        "alpha_t_stat": ratio(coef[0], standard_errors[0]),
    }


def model_summary(model: str, periods: pd.DataFrame) -> dict[str, object]:
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
        "ic_information_ratio": ratio(ic.mean(), ic.std(ddof=1)),
        "ic_t_stat": ratio(ic.mean(), ic.std(ddof=1) / np.sqrt(len(ic))),
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
        "gross_sharpe": ratio(np.sqrt(12) * gross.mean(), gross.std(ddof=1)),
        "net_sharpe": ratio(np.sqrt(12) * net.mean(), net.std(ddof=1)),
        "benchmark_sharpe": ratio(np.sqrt(12) * benchmark.mean(), benchmark.std(ddof=1)),
        "information_ratio": ratio(np.sqrt(12) * active.mean(), active.std(ddof=1)),
        "hit_rate": float((active > 0).mean()),
        **market_exposure(net, benchmark),
        "max_drawdown": max_drawdown(net),
        "benchmark_max_drawdown": max_drawdown(benchmark),
        "mean_turnover": float(periods.turnover.mean()),
        "annualized_cost_drag": float(periods.transaction_cost.mean() * 12),
        "gross_terminal_growth": float((1 + gross).prod() - 1),
        "net_terminal_growth": float((1 + net).prod() - 1),
        "benchmark_terminal_growth": float((1 + benchmark).prod() - 1),
    }


def regime_summary(periods: pd.DataFrame) -> pd.DataFrame:
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


def monitoring_summary(periods: pd.DataFrame, window: int) -> pd.DataFrame:
    """Compare recent ranking quality with the model's earlier record and assign a status.

    The last ``window`` folds are tested against every fold before them. A monthly Rank IC
    has a standard deviation near 0.10, so a six-month mean below zero is common by chance;
    the status therefore depends on how many standard errors the drop is, not its sign alone.

    ``degraded``: the recent mean is more than two standard errors below the earlier mean.
    ``watch``: it is more than one standard error below, or below zero.
    ``healthy``: neither.
    """
    rows: list[dict[str, object]] = []
    for model, model_periods in periods.groupby("model", sort=False):
        ordered = model_periods.sort_values("date")
        recent = ordered.tail(window)
        earlier = ordered.iloc[: max(len(ordered) - window, 0)]
        reference = earlier if len(earlier) >= 2 else ordered
        historical = float(reference.rank_ic.mean())
        recent_ic = float(recent.rank_ic.mean())
        standard_error = float(reference.rank_ic.std(ddof=1) / np.sqrt(max(len(recent), 1)))
        z_score = (recent_ic - historical) / standard_error if standard_error > 0 else 0.0
        if z_score < -2:
            status = "degraded"
        elif z_score < -1 or recent_ic < 0:
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
                "change_z": float(z_score),
                "recent_positive_ic_rate": float((recent.rank_ic > 0).mean()),
                "recent_q1_q5_spread": float(recent.q1_q5_spread.mean()),
                "recent_turnover": float(recent.turnover.mean()),
            }
        )
    return pd.DataFrame(rows)


def population_stability(reference: pd.Series, recent: pd.Series, bins: int = 10) -> float:
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


NOMINAL_FEATURES = ("dollar_volume_20",)


def feature_drift(panel: pd.DataFrame, recent_sessions: int = 63) -> pd.DataFrame:
    """Raw feature distributions over the last quarter compared with all prior history.

    Models see within-date ranks, so a drifting raw level does not reach them directly.
    Drift still matters: it says today's market looks unlike most training data.
    """
    complete = panel.dropna(subset=FEATURE_COLUMNS).copy()
    # Dollar volume grows with prices over a decade, so its raw level always "drifts".
    # Measure it relative to each day's median instead: that is relative liquidity.
    for feature in NOMINAL_FEATURES:
        complete[feature] = complete[feature] / complete.groupby("date")[feature].transform("median")
    dates = pd.DatetimeIndex(complete.date.unique()).sort_values()
    cutoff = dates[-min(recent_sessions, len(dates))]
    reference = complete.loc[complete.date < cutoff]
    recent = complete.loc[complete.date >= cutoff]
    rows = []
    for feature in FEATURE_COLUMNS:
        psi = population_stability(reference[feature], recent[feature])
        spread = reference[feature].std(ddof=1)
        rows.append(
            {
                "feature": feature,
                "psi": psi,
                "reference_median": float(reference[feature].median()),
                "recent_median": float(recent[feature].median()),
                "median_shift_sd": ratio(
                    recent[feature].median() - reference[feature].median(), spread
                )
                if spread > 0
                else 0.0,
                "status": "shifted" if psi >= 0.25 else "moderate" if psi >= 0.1 else "stable",
                "relative_to_date_median": feature in NOMINAL_FEATURES,
            }
        )
    return pd.DataFrame(rows).sort_values("psi", ascending=False)


def sector_summary(history: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
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


def forward_sector_excess(panel: pd.DataFrame, horizon: int) -> pd.Series:
    """Forward return over ``horizon`` sessions minus the sector's equal-weight mean."""
    forward = panel.groupby("ticker").adjusted_close.transform(
        lambda values: values.shift(-horizon) / values - 1
    )
    return forward - forward.groupby([panel.date, panel.sector]).transform("mean")


def signal_decay(
    panel: pd.DataFrame, history: pd.DataFrame, horizons: tuple[int, ...] = DECAY_HORIZONS
) -> pd.DataFrame:
    """Mean Rank IC of each model's fold scores against outcomes at several horizons.

    Evaluation only: the models are trained on the 20-session target. A signal whose IC
    falls quickly past 20 sessions is short-lived; one that holds is slower-moving.
    """
    outcomes = panel.loc[:, ["date", "ticker"]].copy()
    for horizon in horizons:
        outcomes[f"h{horizon}"] = forward_sector_excess(panel, horizon).to_numpy()
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
                    "ic_t_stat": ratio(ic.mean(), ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 1 else 0.0,
                }
            )
    return pd.DataFrame(rows)


def add_significance(summaries: pd.DataFrame) -> pd.DataFrame:
    """Two-sided p-values for mean Rank IC, with a Holm adjustment across the models.

    Comparing several models and reporting the best inflates its apparent
    significance; the Holm step-down adjustment accounts for that without assuming
    the models are independent.
    """
    result = summaries.copy()
    degrees = (result.folds - 1).clip(lower=1)
    result["p_value"] = 2 * stats.t.sf(result.ic_t_stat.abs(), degrees)
    order = result.p_value.sort_values().index
    count = len(order)
    running = 0.0
    adjusted = {}
    for position, label in enumerate(order):
        running = max(running, min(1.0, (count - position) * result.at[label, "p_value"]))
        adjusted[label] = running
    result["p_value_holm"] = pd.Series(adjusted)
    return result
