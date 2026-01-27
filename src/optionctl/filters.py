"""Filtering functions for identifying penny option candidates."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def is_penny_option(ask: float, max_price: float = 0.01) -> bool:
    """Check if an option qualifies as a penny option.

    Args:
        ask: The ask price of the option contract.
        max_price: Maximum price threshold (default $0.01).

    Returns:
        True if the ask is at or below max_price and greater than zero.
    """
    return 0 < ask <= max_price


def volume_oi_ratio(volume: int, open_interest: int) -> float:
    """Calculate the volume-to-open-interest ratio.

    A high ratio indicates unusual trading activity relative to existing
    positions, which can signal smart money or a catalyst.

    Args:
        volume: Number of contracts traded today.
        open_interest: Number of outstanding contracts.

    Returns:
        The ratio, or 0.0 if inputs are invalid.
    """
    if open_interest <= 0 or volume < 0:
        return 0.0
    return volume / open_interest


def proximity_pct(underlying_price: float, strike: float) -> float:
    """Calculate how far the strike is from the underlying price as a percentage.

    Lower values mean the strike is closer to the current price, making it
    more likely to move in-the-money.

    Args:
        underlying_price: Current price of the underlying stock.
        strike: Strike price of the option.

    Returns:
        Distance as a percentage of the underlying price.
    """
    if underlying_price <= 0:
        return math.inf
    return abs(strike - underlying_price) / underlying_price * 100


def apply_filters(
    calls_df: pd.DataFrame,
    underlying_price: float,
    max_price: float = 0.01,
    min_volume: int = 100,
) -> pd.DataFrame:
    """Apply penny option filters to a DataFrame of call options.

    Args:
        calls_df: DataFrame from yfinance option_chain().calls.
        underlying_price: Current price of the underlying.
        max_price: Maximum ask price for penny options.
        min_volume: Minimum contract volume.

    Returns:
        Filtered DataFrame with only qualifying contracts.
    """
    df = calls_df.copy()

    # Drop rows with missing critical data
    df = df.dropna(subset=["ask", "volume", "openInterest"])

    # Penny price filter
    df = df[(df["ask"] > 0) & (df["ask"] <= max_price)]

    # Volume filter
    df = df[df["volume"] >= min_volume]

    # OTM only (not in the money)
    if "inTheMoney" in df.columns:
        df = df[~df["inTheMoney"]]

    if df.empty:
        return df

    # Add computed columns
    df = df.copy()
    df["volumeOiRatio"] = [
        volume_oi_ratio(int(v), int(oi))
        for v, oi in zip(df["volume"], df["openInterest"], strict=True)
    ]
    df["proximityPct"] = [proximity_pct(underlying_price, s) for s in df["strike"]]

    return df
