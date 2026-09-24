"""Declared universes with a GICS-style sector mapping.

These lists are today's large-cap constituents written down by hand. They are not a
historical index-membership file, so every study built on them carries survivorship
bias: companies that fell out of the large-cap group since 2014 are absent.
"""

from __future__ import annotations

_US_LARGE_CAP = {
    "Information Technology": "AAPL MSFT NVDA AVGO ORCL CRM ADBE CSCO ACN IBM INTU TXN QCOM AMD AMAT MU",
    "Communication Services": "GOOGL META NFLX DIS CMCSA T VZ TMUS",
    "Consumer Discretionary": "AMZN TSLA HD MCD NKE LOW SBUX BKNG TJX GM",
    "Consumer Staples": "WMT PG COST KO PEP PM MO MDLZ CL",
    "Health Care": "LLY UNH JNJ ABBV MRK TMO ABT PFE DHR AMGN BMY GILD MDT CVS",
    "Financials": "JPM BAC WFC GS MS C BLK SCHW AXP SPGI CB PGR",
    "Industrials": "CAT GE HON UNP UPS RTX LMT DE BA MMM",
    "Energy": "XOM CVX COP SLB EOG PSX",
    "Utilities": "NEE DUK SO D",
    "Real Estate": "PLD AMT CCI SPG",
    "Materials": "LIN SHW APD ECL NEM",
}

US_LARGE_CAP: dict[str, str] = {
    ticker: sector for sector, tickers in _US_LARGE_CAP.items() for ticker in tickers.split()
}

STARTER_30 = [
    "AAPL", "ADBE", "AVGO", "CRM", "MSFT", "NVDA", "AMZN", "HD", "MCD", "NKE",
    "GOOGL", "META", "NFLX", "JPM", "BAC", "GS", "MS", "UNH", "JNJ", "LLY",
    "PFE", "XOM", "CVX", "SLB", "COST", "WMT", "PG", "CAT", "HON", "GE",
]

UNIVERSES: dict[str, dict[str, object]] = {
    "us_large_cap": {
        "label": "US Large Cap 98",
        "description": "98 current US large caps across all 11 sectors.",
        "tickers": list(US_LARGE_CAP),
    },
    "starter_30": {
        "label": "Starter 30",
        "description": "30 mega caps across 8 sectors. Fast to download.",
        "tickers": STARTER_30,
    },
}

# Retained for callers of the original API.
DEFAULT_UNIVERSE: dict[str, str] = {ticker: US_LARGE_CAP[ticker] for ticker in STARTER_30}


def sectors_for(tickers: list[str]) -> dict[str, str]:
    """Return known sectors and place user-supplied tickers in a visible fallback bucket."""
    return {ticker.upper(): US_LARGE_CAP.get(ticker.upper(), "Unclassified") for ticker in tickers}
