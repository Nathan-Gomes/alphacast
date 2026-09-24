from alphacast import ResearchConfig, run_research, run_study
from alphacast.data import synthetic_prices


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


def test_all_supported_models_share_one_research_contract():
    config = ResearchConfig(
        models=("momentum", "ridge", "elastic_net", "random_forest"),
        minimum_train_sessions=252,
    )
    run = run_research(synthetic_prices(sessions=700, securities=15), source="synthetic", config=config)
    assert set(run.summaries.model) == set(config.models)
    assert set(run.periods.model) == set(config.models)
    assert run.periods.groupby("model").date.nunique().nunique() == 1
    assert set(run.regimes.model) == set(config.models)
    assert set(run.monitoring.model) == set(config.models)
