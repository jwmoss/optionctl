"""Tests for the filters module."""

import math

import pandas as pd
import pytest

from optionctl.filters import apply_filters, is_penny_option, proximity_pct, volume_oi_ratio

# ---------------------------------------------------------------------------
# is_penny_option — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "max_price", "expected"),
    [
        (0.01, 0.01, True),
        (0.005, 0.01, True),
        (0.02, 0.01, False),
        (0.0, 0.01, False),
        (0.05, 0.05, True),
        (0.06, 0.05, False),
    ],
    ids=[
        "at-threshold",
        "below-threshold",
        "above-threshold",
        "zero-price",
        "custom-max-at",
        "custom-max-above",
    ],
)
def test_is_penny_option(price, max_price, expected):
    assert is_penny_option(price, max_price=max_price) is expected


# ---------------------------------------------------------------------------
# volume_oi_ratio — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("volume", "oi", "expected"),
    [
        (500, 100, 5.0),
        (500, 0, 0.0),
        (500, -1, 0.0),
        (0, 100, 0.0),
    ],
    ids=["normal", "zero-oi", "negative-oi", "zero-volume"],
)
def test_volume_oi_ratio(volume, oi, expected):
    assert volume_oi_ratio(volume, oi) == expected


# ---------------------------------------------------------------------------
# proximity_pct — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "strike", "expected"),
    [
        (100.0, 110.0, 10.0),
        (100.0, 95.0, 5.0),
        (100.0, 100.0, 0.0),
        (0.0, 100.0, math.inf),
    ],
    ids=["above", "below", "at-money", "zero-price"],
)
def test_proximity_pct(price, strike, expected):
    assert proximity_pct(price, strike) == expected


# ---------------------------------------------------------------------------
# apply_filters
# ---------------------------------------------------------------------------


def test_apply_filters_basic():
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


def test_apply_filters_lastprice_fallback():
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
    assert len(result) == 1
    assert result.iloc[0]["strike"] == 130.0
    assert result.iloc[0]["_price"] == 0.01


def test_apply_filters_no_matches():
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


def test_apply_filters_uses_make_calls_df(make_calls_df):
    """Demonstrate using the conftest factory fixture."""
    df = make_calls_df(
        strikes=[100.0, 200.0],
        asks=[0.01, 0.01],
        volumes=[500, 50],
        open_interests=[100, 200],
    )
    result = apply_filters(df, underlying_price=50.0, max_price=0.01, min_volume=100)
    assert len(result) == 1
    assert result.iloc[0]["strike"] == 100.0
