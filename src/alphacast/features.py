"""Point-in-time feature and target construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = ["momentum_12_1", "return_63", "volatility_20", "drawdown_63", "market_relative_63"]
TARGET_COLUMN = "forward_sector_excess_20"


def build_panel(prices: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """Build trailing features and a future target without aligning future data to features."""
    required = {"date", "ticker", "sector", "adjusted_close"}
    if missing := required - set(prices.columns):
        raise ValueError(f"Missing price columns: {', '.join(sorted(missing))}")
    panel = prices.sort_values(["ticker", "date"]).copy()
    grouped = panel.groupby("ticker", group_keys=False)
    panel["daily_return"] = grouped.adjusted_close.pct_change()
    panel["return_21"] = grouped.adjusted_close.pct_change(21)
    panel["return_63"] = grouped.adjusted_close.pct_change(63)
    panel["return_126"] = grouped.adjusted_close.pct_change(126)
    panel["momentum_12_1"] = panel["return_126"] - panel["return_21"]
    panel["volatility_20"] = grouped.daily_return.transform(lambda values: values.rolling(20).std()) * np.sqrt(252)
    rolling_peak = grouped.adjusted_close.transform(lambda values: values.rolling(63).max())
    panel["drawdown_63"] = panel.adjusted_close / rolling_peak - 1
    panel["market_return_63"] = panel.groupby("date").return_63.transform("mean")
    panel["market_relative_63"] = panel.return_63 - panel.market_return_63

    # shift(-horizon) means the value attached to t uses closes t+1 through t+horizon.
    panel["forward_return_20"] = grouped.adjusted_close.pct_change(horizon).shift(-horizon)
    panel["sector_forward_return_20"] = panel.groupby(["date", "sector"]).forward_return_20.transform("mean")
    panel[TARGET_COLUMN] = panel.forward_return_20 - panel.sector_forward_return_20
    return panel.drop(columns=["daily_return", "return_21", "return_126", "market_return_63"])


def research_ready(panel: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows whose trailing features and already-defined target are complete."""
    return panel.dropna(subset=[*FEATURE_COLUMNS, TARGET_COLUMN]).copy()
