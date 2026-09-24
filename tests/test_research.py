import pandas as pd

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


def test_ensemble_averages_member_ranks_without_fitting():
    from alphacast.research import ensemble_scores

    config = ResearchConfig(models=("ridge", "elastic_net", "ensemble"), minimum_train_sessions=252)
    run = run_research(synthetic_prices(sessions=700, securities=15), source="synthetic", config=config)
    assert set(run.summaries.model) == {"ridge", "elastic_net", "ensemble"}
    live = run.live.pivot(index="ticker", columns="model", values="score")
    expected = ensemble_scores([live.ridge, live.elastic_net])
    assert (live.ensemble - expected).abs().max() < 1e-12
    assert run.live.loc[run.live.model == "ensemble", "predicted_relative_return"].isna().all()


def test_placebo_labels_leave_no_signal():
    """Shuffle prices across tickers within each date: any skill left would be leakage."""
    import numpy as np

    prices = synthetic_prices(sessions=700, securities=20)
    rng = np.random.default_rng(3)
    # Permute each date's daily returns across tickers, so tomorrow is unrelated to today.
    wide = prices.pivot(index="date", columns="ticker", values="adjusted_close")
    returns = wide.pct_change().fillna(0.0).to_numpy()
    shuffled = np.array([rng.permutation(row) for row in returns])
    rebuilt = 100 * np.cumprod(1 + shuffled, axis=0)
    placebo = prices.copy()
    placebo["adjusted_close"] = (
        pd.DataFrame(rebuilt, index=wide.index, columns=wide.columns)
        .stack()
        .reindex(pd.MultiIndex.from_frame(prices[["date", "ticker"]]))
        .to_numpy()
    )
    config = ResearchConfig(models=("ridge", "random_forest"), minimum_train_sessions=252)
    run = run_research(placebo, source="synthetic", config=config)
    for row in run.summaries.itertuples():
        assert abs(row.ic_t_stat) < 3, f"{row.model} found signal in shuffled data: t={row.ic_t_stat:.2f}"


def test_signal_decay_matches_the_headline_ic_at_the_target_horizon():
    config = ResearchConfig(models=("momentum", "ridge"), minimum_train_sessions=252)
    run = run_research(synthetic_prices(sessions=700, securities=15), source="synthetic", config=config)
    decay = run.decay.set_index(["model", "horizon"])
    assert set(decay.index.get_level_values("horizon")) == {5, 10, 20, 40, 60}
    for model in ("momentum", "ridge"):
        headline = run.summaries.set_index("model").loc[model, "mean_rank_ic"]
        assert abs(decay.loc[(model, 20), "mean_rank_ic"] - headline) < 1e-9


def test_quarterly_rebalancing_trades_only_every_third_month():
    config = ResearchConfig(models=("momentum",), minimum_train_sessions=252, rebalance_every_folds=3)
    run = run_research(synthetic_prices(sessions=700, securities=15), source="synthetic", config=config)
    turnover = run.periods.sort_values("date").turnover.reset_index(drop=True)
    assert (turnover[[i for i in range(len(turnover)) if i % 3]] == 0).all()


def test_neutralized_scores_are_uncorrelated_with_volatility():
    import numpy as np

    from alphacast.research import neutralize

    rng = np.random.default_rng(4)
    vol = pd.Series(rng.uniform(0.1, 0.6, 200))
    scores = pd.Series(2.0 * vol.rank(pct=True) + rng.normal(0, 0.1, 200))
    residual = neutralize(scores, vol)
    assert abs(np.corrcoef(residual, vol.rank(pct=True))[0, 1]) < 1e-9
    assert abs(np.corrcoef(scores, vol.rank(pct=True))[0, 1]) > 0.9


def test_trailing_betas_average_to_about_one_against_the_equal_weight_universe():
    from alphacast.features import build_panel
    from alphacast.research import trailing_betas

    betas = trailing_betas(build_panel(synthetic_prices(sessions=400, securities=20)))
    assert len(betas) == 20
    assert abs(betas.mean() - 1.0) < 1e-9
