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
RANK_COLUMNS = [f"rank_{column}" for column in FEATURE_COLUMNS]

FEATURE_LABELS = {
    "return_21": "1M return",
    "return_63": "3M return",
    "return_126": "6M return",
    "momentum_12_1": "12-1 momentum",
    "volatility_20": "20D volatility",
    "volatility_60": "60D volatility",
    "downside_volatility_60": "60D downside vol",
    "drawdown_252": "12M drawdown",
    "distance_high_252": "Distance from 52W high",
    "ma_ratio_50_200": "50/200 MA spread",
    "dollar_volume_20": "20D dollar volume",
    "volume_ratio_20": "Relative volume",
    "market_relative_63": "3M vs market",
    "sector_relative_63": "3M vs sector",
}

# Descriptive composites for the screener. Each is the mean cross-sectional percentile
# of its members; a minus sign means lower raw values score higher. They summarise a
# security's profile and are not the weights any model uses.
FACTOR_GROUPS: dict[str, list[str]] = {
    "momentum": ["return_126", "momentum_12_1", "ma_ratio_50_200"],
    "relative_strength": ["market_relative_63", "sector_relative_63"],
    "low_risk": ["-volatility_20", "-volatility_60", "-downside_volatility_60", "drawdown_252"],
    "liquidity": ["dollar_volume_20"],
}


def build_panel(prices: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """Build features known at close ``t`` and a target beginning at ``t + 1``."""
    required = {"date", "ticker", "sector", "adjusted_close", "volume"}
    if missing := required - set(prices.columns):
        raise ValueError(f"Missing price columns: {', '.join(sorted(missing))}")
    if horizon < 1:
        raise ValueError("Forward horizon must be positive.")
    panel = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
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
    panel["forward_return_20"] = grouped.adjusted_close.transform(
        lambda values: values.shift(-horizon) / values - 1
    )
    panel["sector_forward_return_20"] = panel.groupby(["date", "sector"]).forward_return_20.transform(
        "mean"
    )
    panel[TARGET_COLUMN] = panel.forward_return_20 - panel.sector_forward_return_20
    return panel.drop(columns=["daily_return", "sector_return_63"], errors="ignore")


def research_ready(panel: pd.DataFrame) -> pd.DataFrame:
    """Keep dates where all trailing inputs and the realized forward label exist."""
    return panel.dropna(subset=[*FEATURE_COLUMNS, TARGET_COLUMN]).copy()


def latest_cross_section(panel: pd.DataFrame) -> pd.DataFrame:
    """The most recent session with complete trailing inputs; its outcome is unknown."""
    scoreable = panel.dropna(subset=FEATURE_COLUMNS)
    if scoreable.empty:
        raise ValueError("No session has a complete set of trailing features.")
    latest = scoreable.date.max()
    return scoreable.loc[scoreable.date == latest].copy()


def cross_sectional_ranks(rows: pd.DataFrame) -> pd.DataFrame:
    """Rank each feature within its own date, centred on zero.

    Raw levels drift over a decade (dollar volume grows, volatility regimes shift). A
    within-date rank keeps only the ordering that a cross-sectional model can use.
    """
    if set(RANK_COLUMNS).issubset(rows.columns):
        return rows[RANK_COLUMNS].set_axis(FEATURE_COLUMNS, axis=1)
    ranked = rows.groupby("date")[FEATURE_COLUMNS].rank(pct=True) - 0.5
    return ranked.fillna(0.0)


def with_cross_sectional_ranks(rows: pd.DataFrame) -> pd.DataFrame:
    """Attach within-date ranks once so every fold and model can reuse them.

    A rank depends only on its own date, never on the training window, so computing it
    once for the whole panel is identical to computing it inside each fit.
    """
    ranked = rows.groupby("date")[FEATURE_COLUMNS].rank(pct=True).sub(0.5).fillna(0.0)
    return rows.assign(**{f"rank_{column}": ranked[column] for column in FEATURE_COLUMNS})


def factor_percentiles(rows: pd.DataFrame) -> pd.DataFrame:
    """Descriptive composite percentiles for one cross-section, scaled 0-100."""
    result = pd.DataFrame(index=rows.index)
    for name, members in FACTOR_GROUPS.items():
        parts = []
        for member in members:
            column = member.lstrip("-")
            ranked = rows[column].rank(pct=True)
            parts.append(1 - ranked if member.startswith("-") else ranked)
        result[name] = pd.concat(parts, axis=1).mean(axis=1).rank(pct=True) * 100
    return result
