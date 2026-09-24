import numpy as np
import pandas as pd

from alphacast.diagnostics import max_drawdown, monitoring_summary, population_stability


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
