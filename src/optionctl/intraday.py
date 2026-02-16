"""Intraday market-data utilities for zero-DTE signal generation."""

from __future__ import annotations

from datetime import UTC
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

_ET = ZoneInfo("America/New_York")


def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return an OHLCV DataFrame with lowercase column names."""
    if isinstance(df.columns, pd.MultiIndex):
        # Single-ticker downloads can still return a MultiIndex depending on
        # the yfinance version and parameters.
        return df.droplevel(-1, axis=1).rename(columns=lambda c: str(c).lower())
    return df.rename(columns=lambda c: str(c).lower())


def fetch_intraday_bars(
    ticker: str,
    *,
    interval: str = "1m",
    period: str = "2d",
) -> pd.DataFrame:
    """Fetch intraday OHLCV bars and normalize to Eastern Time.

    Args:
        ticker: Underlying symbol.
        interval: Bar interval supported by yfinance (default ``1m``).
        period: Lookback period for bar data (default ``2d``).

    Returns:
        DataFrame indexed by timezone-aware timestamps in ET with lowercase
        columns (``open``, ``high``, ``low``, ``close``, ``volume``).
    """
    bars = yf.download(
        tickers=ticker,
        interval=interval,
        period=period,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if bars.empty:
        return bars

    bars = _normalize_ohlcv_columns(bars)
    if not isinstance(bars.index, pd.DatetimeIndex):
        return bars

    index = bars.index
    if index.tz is None:
        bars.index = index.tz_localize(UTC)
    return bars.tz_convert(_ET)


def to_five_minute_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample one-minute bars to 5-minute OHLCV bars.

    Args:
        bars_1m: One-minute OHLCV bars.

    Returns:
        Five-minute OHLCV bars.
    """
    if bars_1m.empty:
        return bars_1m

    return (
        bars_1m.resample("5min")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
