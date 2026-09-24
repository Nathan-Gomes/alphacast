import numpy as np
import pandas as pd

from alphacast.diagnostics import (
    add_significance,
    market_exposure,
    max_drawdown,
    monitoring_summary,
    population_stability,
)


def test_population_stability_is_near_zero_for_the_same_distribution_and_large_for_a_shift():
    rng = np.random.default_rng(0)
    reference = pd.Series(rng.normal(0, 1, 5000))
    assert population_stability(reference, pd.Series(rng.normal(0, 1, 2000))) < 0.02
    assert population_stability(reference, pd.Series(rng.normal(1.5, 1, 2000))) > 0.5


def _periods(ics: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "model": "m",
            "date": pd.date_range("2020-01-31", periods=len(ics), freq="ME"),
            "rank_ic": ics,
            "q1_q5_spread": 0.0,
            "turnover": 0.3,
        }
    )


def test_monitoring_statuses_follow_the_declared_thresholds():
    steady = [0.05, 0.03] * 12
    healthy = monitoring_summary(_periods(steady), window=6).iloc[0]
    assert healthy.status == "healthy"
    degraded = monitoring_summary(_periods(steady[:-6] + [-0.02] * 6), window=6).iloc[0]
    assert degraded.status == "degraded"
    # Recent IC positive but more than one standard error below the full-sample mean.
    calm = [0.06, 0.04] * 12
    watch = monitoring_summary(_periods(calm[:-6] + [0.005] * 6), window=6).iloc[0]
    assert watch.recent_mean_rank_ic > 0
    assert watch.status == "watch"


def test_max_drawdown_counts_the_start_as_a_peak():
    assert abs(max_drawdown(pd.Series([-0.1, 0.0])) - (-0.1)) < 1e-12
    assert abs(max_drawdown(pd.Series([0.1, -0.5, 0.2])) - (-0.5)) < 1e-12


def test_holm_adjustment_multiplies_the_smallest_p_value_by_the_number_of_models():
    summaries = pd.DataFrame({"model": list("abc"), "folds": 114, "ic_t_stat": [2.41, 1.0, 0.2]})
    result = add_significance(summaries).set_index("model")
    assert 0.015 < result.at["a", "p_value"] < 0.02
    assert abs(result.at["a", "p_value_holm"] - 3 * result.at["a", "p_value"]) < 1e-12
    assert (result.p_value_holm >= result.p_value).all()
    assert result.p_value_holm.is_monotonic_increasing


def test_market_exposure_recovers_a_known_beta_and_alpha():
    rng = np.random.default_rng(1)
    bench = pd.Series(rng.normal(0.01, 0.04, 240))
    returns = 0.002 + 1.3 * bench + pd.Series(rng.normal(0, 0.001, 240))
    exposure = market_exposure(returns, bench)
    assert abs(exposure["beta"] - 1.3) < 0.01
    assert abs(exposure["alpha_annualized"] - 0.024) < 0.003
    assert exposure["alpha_t_stat"] > 10


def test_nominal_growth_in_dollar_volume_is_not_reported_as_drift():
    from alphacast.data import synthetic_prices
    from alphacast.diagnostics import feature_drift
    from alphacast.features import build_panel

    prices = synthetic_prices(sessions=500, securities=20)
    # Inflate every volume steadily over time: relative liquidity is unchanged.
    growth = prices.date.rank(method="dense") / prices.date.nunique()
    prices["volume"] = (prices.volume * (1 + 3 * growth)).round()
    drift = feature_drift(build_panel(prices)).set_index("feature")
    assert drift.at["dollar_volume_20", "psi"] < 0.1
    assert drift.at["dollar_volume_20", "relative_to_date_median"]
