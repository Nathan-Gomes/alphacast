from alphacast import run_study


def test_synthetic_study_is_reproducible_and_out_of_sample():
    first = run_study("ridge")
    second = run_study("ridge")
    assert first.observations > 12
    assert first.mean_rank_ic == second.mean_rank_ic
    assert first.monthly.date.is_monotonic_increasing


def test_momentum_baseline_runs_under_same_validation_rules():
    result = run_study("momentum")
    assert result.observations > 12
    assert result.monthly.securities.min() >= 10
