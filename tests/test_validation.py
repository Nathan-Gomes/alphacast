from alphacast.data import synthetic_prices
from alphacast.features import build_panel, research_ready
from alphacast.validation import expanding_folds, training_rows


def test_embargo_removes_overlapping_forward_labels_from_training():
    panel = research_ready(build_panel(synthetic_prices(sessions=550, securities=20)))
    fold = expanding_folds(panel, minimum_train_sessions=252, embargo_sessions=20)[0]
    training = training_rows(panel, fold)
    assert training.date.max() == fold.train_end
    assert training.date.max() < fold.test_date


def test_folds_move_forward_in_time():
    panel = research_ready(build_panel(synthetic_prices(sessions=550, securities=20)))
    folds = expanding_folds(panel)
    assert all(left.test_date < right.test_date for left, right in pairwise(folds))
from itertools import pairwise


def test_a_month_truncated_by_missing_labels_is_not_a_fold():
    full = build_panel(synthetic_prices(sessions=800, securities=20))
    panel = research_ready(full)
    folds = expanding_folds(panel, calendar=full.date.unique())
    last_ready = panel.date.max()
    calendar = full.date.drop_duplicates()
    same_month = calendar[calendar.dt.to_period("M") == last_ready.to_period("M")]
    if same_month.max() > last_ready:
        assert folds[-1].test_date < last_ready.to_period("M").start_time


def test_vectorised_sampler_matches_reference_selection():
    from alphacast.validation import TrainingSampler, sampled_training_rows

    panel = research_ready(build_panel(synthetic_prices(sessions=700, securities=12)))
    sampler = TrainingSampler(panel, 5)
    for fold in expanding_folds(panel)[::4]:
        expected = sampled_training_rows(panel, fold.train_end, 5)
        assert sampler.rows(fold.train_end).index.equals(expected.index)
