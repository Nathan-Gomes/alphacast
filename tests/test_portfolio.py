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
