"""Point-in-time price and volume features plus forward relative-return labels."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "return_21",
    "return_63",
    "return_126",
    "momentum_12_1",
    "volatility_20",
    "volatility_60",
    "downside_volatility_60",
    "drawdown_252",
    "distance_high_252",
    "ma_ratio_50_200",
    "dollar_volume_20",
    "volume_ratio_20",
    "market_relative_63",
    "sector_relative_63",
]
TARGET_COLUMN = "forward_sector_excess_20"


def build_panel(prices: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """Build features known at close ``t`` and a target beginning at ``t + 1``."""
    required = {"date", "ticker", "sector", "adjusted_close", "volume"}
    if missing := required - set(prices.columns):
        raise ValueError(f"Missing price columns: {', '.join(sorted(missing))}")
    if horizon < 1:
        raise ValueError("Forward horizon must be positive.")
    panel = prices.sort_values(["ticker", "date"]).copy()
    panel["date"] = pd.to_datetime(panel["date"])
    grouped = panel.groupby("ticker", group_keys=False)
    panel["daily_return"] = grouped.adjusted_close.pct_change()
    for period in (21, 63, 126):
        panel[f"return_{period}"] = grouped.adjusted_close.pct_change(period)
    panel["momentum_12_1"] = grouped.adjusted_close.transform(
        lambda values: values.shift(21) / values.shift(252) - 1
    )
    panel["volatility_20"] = grouped.daily_return.transform(
        lambda values: values.rolling(20).std() * np.sqrt(252)
    )
    panel["volatility_60"] = grouped.daily_return.transform(
        lambda values: values.rolling(60).std() * np.sqrt(252)
    )
    panel["downside_volatility_60"] = grouped.daily_return.transform(
        lambda values: values.clip(upper=0).rolling(60).std() * np.sqrt(252)
    )
    peak_252 = grouped.adjusted_close.transform(lambda values: values.rolling(252).max())
    panel["drawdown_252"] = panel.adjusted_close / peak_252 - 1
    panel["distance_high_252"] = panel["drawdown_252"]
    moving_50 = grouped.adjusted_close.transform(lambda values: values.rolling(50).mean())
    moving_200 = grouped.adjusted_close.transform(lambda values: values.rolling(200).mean())
    panel["ma_ratio_50_200"] = moving_50 / moving_200 - 1
    panel["dollar_volume_20"] = (panel.adjusted_close * panel.volume).groupby(panel.ticker).transform(
        lambda values: values.rolling(20).mean()
    )
    volume_60 = grouped.volume.transform(lambda values: values.rolling(60).mean())
    panel["volume_ratio_20"] = panel.volume / volume_60 - 1
    panel["market_return_63"] = panel.groupby("date").return_63.transform("mean")
    market_daily_return = panel.groupby("date").daily_return.mean()
    market_volatility_20 = market_daily_return.rolling(20).std() * np.sqrt(252)
    panel["market_volatility_20"] = panel.date.map(market_volatility_20)
    panel["market_relative_63"] = panel.return_63 - panel.market_return_63
    panel["sector_return_63"] = panel.groupby(["date", "sector"]).return_63.transform("mean")
    panel["sector_relative_63"] = panel.return_63 - panel.sector_return_63

    # This attaches the return from t to t + horizon to the decision made at t.
    # No feature above is shifted backward from a future date.
    panel["forward_return_20"] = grouped.adjusted_close.pct_change(horizon).shift(-horizon)
    panel["sector_forward_return_20"] = panel.groupby(["date", "sector"]).forward_return_20.transform(
        "mean"
    )
    panel[TARGET_COLUMN] = panel.forward_return_20 - panel.sector_forward_return_20
    return panel.drop(columns=["daily_return", "sector_return_63"], errors="ignore")


def research_ready(panel: pd.DataFrame) -> pd.DataFrame:
    """Keep dates where all trailing inputs and the realized forward label exist."""
    return panel.dropna(subset=[*FEATURE_COLUMNS, TARGET_COLUMN]).copy()
