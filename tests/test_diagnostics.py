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
    # A collapse many standard errors below the earlier record.
    degraded = monitoring_summary(_periods(steady[:-6] + [-0.02] * 6), window=6).iloc[0]
    assert degraded.status == "degraded"
    assert degraded.change_z < -2
    # Noisy history: a small negative six-month mean is within noise, so only "watch".
    noisy = [0.15, -0.09] * 12
    dip = monitoring_summary(_periods(noisy[:-6] + [-0.01] * 6), window=6).iloc[0]
    assert -2 < dip.change_z < 0
    assert dip.status == "watch"
    # Positive recent IC between one and two standard errors below the earlier record.
    calm = [0.09, 0.03] * 12
    slip = monitoring_summary(_periods(calm[:-6] + [0.02, 0.06] * 3), window=6).iloc[0]
    assert slip.recent_mean_rank_ic > 0
    assert -2 < slip.change_z < -1
    assert slip.status == "watch"


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


def test_block_bootstrap_interval_brackets_the_mean_and_widens_with_noise():
    import numpy as np
    import pandas as pd

    from alphacast.diagnostics import block_bootstrap_interval

    rng = np.random.default_rng(3)
    calm = pd.Series(0.03 + rng.normal(0, 0.05, 120))
    noisy = pd.Series(0.03 + rng.normal(0, 0.15, 120))
    low, high = block_bootstrap_interval(calm)
    assert low < calm.mean() < high
    noisy_low, noisy_high = block_bootstrap_interval(noisy)
    assert noisy_high - noisy_low > 2 * (high - low)
    # Deterministic for a fixed seed, and undefined for too few months.
    assert block_bootstrap_interval(calm) == (low, high)
    assert np.isnan(block_bootstrap_interval(calm.head(5))[0])


def test_newey_west_matches_the_plain_t_without_lags_and_shrinks_it_under_overlap():
    import numpy as np
    import pandas as pd

    from alphacast.diagnostics import newey_west_t, ratio

    rng = np.random.default_rng(11)
    iid = pd.Series(0.02 + rng.normal(0, 0.1, 200))
    plain = ratio(iid.mean(), iid.std(ddof=1) / np.sqrt(len(iid)))
    assert abs(newey_west_t(iid, 0) - plain) < 1e-12
    # Sums of three consecutive shocks overlap like 60-session outcomes on monthly folds.
    shocks = rng.normal(0, 0.1, 203)
    overlapping = pd.Series(0.02 + shocks[:-3] + shocks[1:-2] + shocks[2:-1])
    assert newey_west_t(overlapping, 2) < 0.8 * newey_west_t(overlapping, 0)
