import pandas as pd

from alphacast.portfolio import top_ranked_portfolio


def test_first_portfolio_step_does_not_charge_an_arbitrary_initial_turnover_cost():
    rows = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "forward_return_20": [0.03, 0.01, -0.02],
        }
    )
    step, weights = top_ranked_portfolio(
        rows,
        pd.Series([3.0, 2.0, 1.0]),
        None,
        top_n=2,
        transaction_cost_bps=10,
    )
    assert step.turnover == 0.0
    assert step.net_return == step.gross_return
    assert list(weights.index) == ["A", "B"]


def test_rebalance_charges_cost_for_a_changed_holding_set():
    rows = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "forward_return_20": [0.03, 0.01, -0.02],
        }
    )
    step, _ = top_ranked_portfolio(
        rows,
        pd.Series([1.0, 3.0, 2.0]),
        pd.Series({"A": 0.5, "B": 0.5}),
        top_n=2,
        transaction_cost_bps=10,
    )
    assert step.turnover == 0.5
    assert step.transaction_cost == 0.0005
    assert step.net_return == step.gross_return - step.transaction_cost


def test_sector_cap_fills_places_from_other_sectors():
    from alphacast.portfolio import select_top

    rows = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E"],
            "sector": ["Tech", "Tech", "Tech", "Energy", "Health"],
        }
    )
    scores = pd.Series([5.0, 4.0, 3.0, 2.0, 1.0])
    assert list(select_top(rows, scores, top_n=3).ticker) == ["A", "B", "C"]
    assert list(select_top(rows, scores, top_n=3, max_per_sector=1).ticker) == ["A", "D", "E"]
    assert list(select_top(rows, scores, top_n=4, max_per_sector=2).ticker) == ["A", "B", "D", "E"]


def test_holding_a_book_costs_nothing_and_earns_its_names():
    from alphacast.portfolio import hold_portfolio

    rows = pd.DataFrame({"ticker": ["A", "B", "C"], "forward_return_20": [0.03, 0.01, -0.02]})
    step = hold_portfolio(rows, pd.Series({"A": 0.5, "C": 0.5}))
    assert step.turnover == 0.0 and step.transaction_cost == 0.0
    assert abs(step.gross_return - 0.005) < 1e-12
    assert step.net_return == step.gross_return


def test_buffer_keeps_holdings_that_only_slipped_a_little():
    from alphacast.portfolio import select_top

    rows = pd.DataFrame({"ticker": list("ABCDEF"), "sector": ["X"] * 6})
    scores = pd.Series([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    # D and F were held; D is 4th (inside a buffer of 4), F is 6th (outside it).
    picked = select_top(rows, scores, top_n=3, keep={"D", "F"}, keep_within=4)
    assert list(picked.ticker) == ["D", "A", "B"]
    assert list(select_top(rows, scores, top_n=3).ticker) == ["A", "B", "C"]
