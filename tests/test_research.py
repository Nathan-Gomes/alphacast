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


def test_batched_attribution_matches_one_feature_at_a_time():
    import numpy as np

    from alphacast.features import (
        FEATURE_COLUMNS,
        build_panel,
        cross_sectional_ranks,
        research_ready,
    )
    from alphacast.ranking import fit_ranker

    panel = research_ready(build_panel(synthetic_prices(sessions=500, securities=15)))
    train = panel[panel.date < panel.date.max()]
    rows = panel[panel.date == panel.date.max()]
    ranker = fit_ranker("gradient_boosting", train)
    batched = ranker.attribution(rows)
    matrix = cross_sectional_ranks(rows).to_numpy()
    base = ranker.estimator.predict(matrix)
    for position, feature in enumerate(FEATURE_COLUMNS):
        occluded = matrix.copy()
        occluded[:, position] = 0.0
        assert np.allclose(batched[feature], base - ranker.estimator.predict(occluded))


def test_sector_summary_covers_every_model_and_sector():
    config = ResearchConfig(models=("momentum", "ridge"), minimum_train_sessions=252)
    run = run_research(synthetic_prices(sessions=700, securities=24), source="synthetic", config=config)
    sectors = run.sectors
    assert set(sectors.model) == {"momentum", "ridge"}
    assert sectors.groupby("model").sector.nunique().eq(6).all()
    assert sectors.mean_rank_ic.between(-1, 1).all()
    # Active weights across sectors net to zero for a fully invested sleeve.
    assert sectors.groupby("model").mean_active_weight.sum().abs().lt(1e-9).all()
