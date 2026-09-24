"""Market-data ingestion and validation with a deterministic synthetic fallback."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import DataQualityReport

REQUIRED_PRICE_COLUMNS = {"date", "ticker", "sector", "adjusted_close", "volume"}


def synthetic_prices(
    sessions: int = 1_600,
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
            "volume": rng.integers(750_000, 6_000_000, size=sessions * securities),
        }
    )


def validate_price_panel(
    prices: pd.DataFrame,
    *,
    source: str,
    requested_tickers: int | None = None,
    minimum_sessions: int = 300,
    minimum_tickers: int = 10,
) -> DataQualityReport:
    """Reject malformed coverage before it can become a research result."""
    missing = REQUIRED_PRICE_COLUMNS - set(prices.columns)
    if missing:
        raise ValueError(f"Missing market-data columns: {', '.join(sorted(missing))}")
    panel = prices.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    if panel.duplicated(["date", "ticker"]).any():
        raise ValueError("Market data contains duplicate ticker-date observations.")
    if (panel.adjusted_close <= 0).any() or (panel.volume < 0).any():
        raise ValueError("Market data contains non-positive prices or negative volume.")
    sessions = panel.date.nunique()
    tickers = panel.ticker.nunique()
    if sessions < minimum_sessions:
        raise ValueError(f"Need at least {minimum_sessions} sessions; received {sessions}.")
    if tickers < minimum_tickers:
        raise ValueError(f"Need at least {minimum_tickers} securities; received {tickers}.")
    expected = sessions * tickers
    return DataQualityReport(
        source=source,
        requested_tickers=requested_tickers or tickers,
        accepted_tickers=tickers,
        sessions=sessions,
        first_date=panel.date.min(),
        last_date=panel.date.max(),
        missing_observations=expected - len(panel),
    )


def yahoo_prices(
    tickers: list[str],
    sectors: dict[str, str],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    """Download adjusted Yahoo Finance price/volume history into AlphaCast's panel contract.

    Yahoo data is convenient for an educational research prototype, not a point-in-time
    institutional data feed. The caller receives a clean, validated long-form panel.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency failure is environment-specific
        raise RuntimeError("Install the live dependencies to use Yahoo Finance data.") from exc

    normalized = list(dict.fromkeys(ticker.upper().strip() for ticker in tickers if ticker.strip()))
    if len(normalized) < 10:
        raise ValueError("Use at least ten tickers for a cross-sectional ranking study.")
    resolved_sectors = _resolve_yahoo_sectors(yf, normalized, sectors)
    raw = yf.download(
        normalized,
        start=start,
        end=end,
        auto_adjust=True,
        actions=False,
        group_by="ticker",
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise RuntimeError("Yahoo Finance returned no prices for the requested universe.")

    records: list[pd.DataFrame] = []
    for ticker in normalized:
        try:
            frame = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        if "Close" not in frame or "Volume" not in frame:
            continue
        prepared = frame[["Close", "Volume"]].dropna().rename(
            columns={"Close": "adjusted_close", "Volume": "volume"}
        )
        prepared["ticker"] = ticker
        prepared["sector"] = resolved_sectors[ticker]
        prepared["date"] = prepared.index
        records.append(prepared.reset_index(drop=True))
    if not records:
        raise RuntimeError("Yahoo Finance did not return usable close and volume fields.")
    panel = pd.concat(records, ignore_index=True)
    panel = panel[["date", "ticker", "sector", "adjusted_close", "volume"]]
    validate_price_panel(panel, source="yahoo", requested_tickers=len(normalized))
    return panel


def _resolve_yahoo_sectors(yf, tickers: list[str], sectors: dict[str, str]) -> dict[str, str]:
    """Use the declared mapping first, then request Yahoo metadata for custom symbols.

    An unavailable metadata response is represented as ``Unclassified`` rather than
    silently inventing a sector. The relative target then remains a universe-relative
    comparison for that fallback bucket.
    """
    resolved = {ticker: sectors.get(ticker, "Unclassified") for ticker in tickers}
    for ticker in tickers:
        if resolved[ticker] != "Unclassified":
            continue
        try:
            sector = yf.Ticker(ticker).get_info().get("sector")
        except Exception:  # noqa: BLE001 - third-party provider failures are not a stable exception API
            sector = None
        if sector:
            resolved[ticker] = str(sector)
    return resolved
