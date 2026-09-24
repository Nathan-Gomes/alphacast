from alphacast.data import synthetic_prices
from alphacast.features import TARGET_COLUMN, build_panel, research_ready


def test_target_is_attached_to_the_decision_date_not_a_future_feature():
    prices = synthetic_prices(sessions=360, securities=12)
    panel = build_panel(prices, horizon=20)
    ticker = panel.ticker.iloc[0]
    row = panel[(panel.ticker == ticker) & panel[TARGET_COLUMN].notna()].iloc[0]
    series = prices[prices.ticker == ticker].sort_values("date").reset_index(drop=True)
    position = series.index[series.date == row.date][0]
    expected = series.adjusted_close.iloc[position + 20] / series.adjusted_close.iloc[position] - 1
    assert row.forward_return_20 == expected


def test_research_rows_have_all_trailing_inputs_and_one_future_label():
    ready = research_ready(build_panel(synthetic_prices(sessions=400, securities=15)))
    assert not ready.isna().any().any()
    assert (ready[TARGET_COLUMN].abs() < 1).all()
