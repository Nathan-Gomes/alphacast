"""A deterministic synthetic panel used to test the research workflow itself."""

from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_prices(
    sessions: int = 1_100,
    securities: int = 60,
    seed: int = 17,
) -> pd.DataFrame:
    """Create a reproducible multi-sector panel without presenting it as market data."""
    if sessions < 300 or securities < 10:
        raise ValueError("Synthetic research needs at least 300 sessions and 10 securities.")
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-02", periods=sessions)
    tickers = [f"SYN{i:03d}" for i in range(securities)]
    sectors = np.array([f"Sector {i % 6}" for i in range(securities)])
    market = rng.normal(0.00025, 0.009, sessions)
    sector_shocks = rng.normal(0, 0.005, (sessions, 6))
    exposures = rng.normal(1, 0.18, securities)
    quality = rng.normal(0, 0.00013, securities)
    noise = rng.normal(0, 0.012, (sessions, securities))
    returns = market[:, None] * exposures + sector_shocks[:, np.arange(securities) % 6] + quality + noise
    prices = 100 * np.exp(np.cumsum(returns, axis=0))
    return pd.DataFrame(
        {
            "date": np.repeat(dates, securities),
            "ticker": np.tile(tickers, sessions),
            "sector": np.tile(sectors, sessions),
            "adjusted_close": prices.ravel(),
        }
    )
