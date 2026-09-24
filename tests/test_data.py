import pandas as pd
import pytest

from alphacast.data import synthetic_prices, validate_price_panel


def test_quality_report_describes_a_complete_synthetic_panel():
    prices = synthetic_prices(sessions=350, securities=12)
    report = validate_price_panel(prices, source="synthetic")
    assert report.accepted_tickers == 12
    assert report.sessions == 350
    assert report.missing_observations == 0


def test_quality_gate_rejects_duplicate_ticker_date_observations():
    prices = synthetic_prices(sessions=350, securities=12)
    duplicate = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        validate_price_panel(duplicate, source="synthetic")


def test_partially_published_sessions_are_dropped():
    from alphacast.data import drop_incomplete_sessions

    prices = synthetic_prices(sessions=350, securities=20)
    last = prices.date.max()
    partial = prices[(prices.date != last) | prices.ticker.isin(["SYN000", "SYN001"])]
    cleaned, dropped = drop_incomplete_sessions(partial)
    assert dropped == 1
    assert last not in set(cleaned.date)
