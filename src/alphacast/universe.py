"""A transparent starter universe for live-data demonstrations."""

from __future__ import annotations

DEFAULT_UNIVERSE: dict[str, str] = {
    "AAPL": "Information Technology",
    "ADBE": "Information Technology",
    "AVGO": "Information Technology",
    "CRM": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "AMZN": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary",
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    "JPM": "Financials",
    "BAC": "Financials",
    "GS": "Financials",
    "MS": "Financials",
    "UNH": "Health Care",
    "JNJ": "Health Care",
    "LLY": "Health Care",
    "PFE": "Health Care",
    "XOM": "Energy",
    "CVX": "Energy",
    "SLB": "Energy",
    "COST": "Consumer Staples",
    "WMT": "Consumer Staples",
    "PG": "Consumer Staples",
    "CAT": "Industrials",
    "HON": "Industrials",
    "GE": "Industrials",
}


def sectors_for(tickers: list[str]) -> dict[str, str]:
    """Return known sectors and place user-supplied tickers in a visible fallback bucket."""
    return {ticker.upper(): DEFAULT_UNIVERSE.get(ticker.upper(), "Unclassified") for ticker in tickers}
