"""Tests for the filters module."""

import math

import pandas as pd

from optionctl.filters import apply_filters, is_penny_option, proximity_pct, volume_oi_ratio


def test_is_penny_option_at_threshold() -> None:
    assert is_penny_option(0.01) is True


def test_is_penny_option_below_threshold() -> None:
    assert is_penny_option(0.005) is True


def test_is_penny_option_above_threshold() -> None:
    assert is_penny_option(0.02) is False


def test_is_penny_option_zero() -> None:
    assert is_penny_option(0.0) is False


def test_is_penny_option_custom_max() -> None:
    assert is_penny_option(0.05, max_price=0.05) is True
    assert is_penny_option(0.06, max_price=0.05) is False


def test_volume_oi_ratio_normal() -> None:
    assert volume_oi_ratio(500, 100) == 5.0


def test_volume_oi_ratio_zero_oi() -> None:
    assert volume_oi_ratio(500, 0) == 0.0


def test_volume_oi_ratio_negative_oi() -> None:
    assert volume_oi_ratio(500, -1) == 0.0


def test_volume_oi_ratio_zero_volume() -> None:
    assert volume_oi_ratio(0, 100) == 0.0


def test_proximity_pct_above() -> None:
    # Strike 10% above underlying
    result = proximity_pct(100.0, 110.0)
    assert result == 10.0


def test_proximity_pct_below() -> None:
    # Strike 5% below underlying
    result = proximity_pct(100.0, 95.0)
    assert result == 5.0


def test_proximity_pct_at_money() -> None:
    assert proximity_pct(100.0, 100.0) == 0.0


def test_proximity_pct_zero_price() -> None:
    assert proximity_pct(0.0, 100.0) == math.inf


def test_apply_filters_basic() -> None:
    df = pd.DataFrame(
        {
            "strike": [100.0, 110.0, 120.0, 130.0],
            "ask": [0.01, 0.01, 0.05, 0.01],
            "bid": [0.0, 0.0, 0.0, 0.0],
            "lastPrice": [0.01, 0.01, 0.05, 0.01],
            "volume": [200, 50, 300, 500],
            "openInterest": [100, 200, 100, 50],
            "impliedVolatility": [0.5, 0.3, 0.8, 0.6],
            "inTheMoney": [True, False, False, False],
        }
    )
    result = apply_filters(df, underlying_price=95.0, max_price=0.01, min_volume=100)
    # Should filter: strike=100 (ITM), strike=110 (vol<100), strike=120 (ask>0.01)
    # Should keep: strike=130
    assert len(result) == 1
    assert result.iloc[0]["strike"] == 130.0
    assert result.iloc[0]["volumeOiRatio"] == 10.0


def test_apply_filters_lastprice_fallback() -> None:
    """When ask=0 (market closed), lastPrice is used as fallback."""
    df = pd.DataFrame(
        {
            "strike": [130.0, 140.0],
            "ask": [0.0, 0.0],
            "bid": [0.0, 0.0],
            "lastPrice": [0.01, 0.05],
            "volume": [500, 300],
            "openInterest": [100, 50],
            "impliedVolatility": [0.5, 0.6],
            "inTheMoney": [False, False],
        }
    )
    result = apply_filters(df, underlying_price=95.0, max_price=0.01, min_volume=100)
    # strike=130 should match (lastPrice=0.01), strike=140 excluded (lastPrice=0.05)
    assert len(result) == 1
    assert result.iloc[0]["strike"] == 130.0
    assert result.iloc[0]["_price"] == 0.01


def test_apply_filters_no_matches() -> None:
    df = pd.DataFrame(
        {
            "strike": [100.0],
            "ask": [0.05],
            "bid": [0.0],
            "volume": [200],
            "openInterest": [100],
            "impliedVolatility": [0.5],
            "inTheMoney": [False],
        }
    )
    result = apply_filters(df, underlying_price=95.0, max_price=0.01, min_volume=100)
    assert len(result) == 0
