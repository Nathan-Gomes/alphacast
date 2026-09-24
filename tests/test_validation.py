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
