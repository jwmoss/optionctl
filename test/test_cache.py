"""Tests for the cache module."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from optionctl.cache import (
    _is_cache_valid,
    _is_market_open,
    clear_cache,
    get_cache_stats,
    read_chain_cache,
    write_chain_cache,
)

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Use a temporary directory for cache tests."""
    test_cache_dir = tmp_path / "cache" / "chains"
    monkeypatch.setattr("optionctl.cache._CACHE_DIR", test_cache_dir)
    return test_cache_dir


@pytest.fixture
def sample_chain_df():
    """Sample DataFrame mimicking yfinance option chain."""
    return pd.DataFrame(
        {
            "strike": [100.0, 105.0],
            "ask": [0.01, 0.02],
            "bid": [0.0, 0.01],
            "volume": [500, 300],
            "openInterest": [100, 200],
        }
    )


# ---------------------------------------------------------------------------
# _is_market_open tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mock_time", "expected"),
    [
        # Weekday during market hours
        (datetime(2026, 1, 28, 10, 0, tzinfo=_ET), True),  # Wednesday 10am
        (datetime(2026, 1, 28, 15, 30, tzinfo=_ET), True),  # Wednesday 3:30pm
        (datetime(2026, 1, 28, 9, 30, tzinfo=_ET), True),  # Wednesday 9:30am (open)
        (datetime(2026, 1, 28, 16, 0, tzinfo=_ET), True),  # Wednesday 4pm (close)
        # Weekday outside market hours
        (datetime(2026, 1, 28, 9, 0, tzinfo=_ET), False),  # Wednesday 9am (pre-market)
        (datetime(2026, 1, 28, 16, 1, tzinfo=_ET), False),  # Wednesday 4:01pm (after)
        (datetime(2026, 1, 28, 20, 0, tzinfo=_ET), False),  # Wednesday 8pm
        # Weekend
        (datetime(2026, 1, 31, 12, 0, tzinfo=_ET), False),  # Saturday noon
        (datetime(2026, 2, 1, 12, 0, tzinfo=_ET), False),  # Sunday noon
    ],
    ids=[
        "weekday-midday",
        "weekday-afternoon",
        "weekday-open",
        "weekday-close",
        "weekday-premarket",
        "weekday-afterhours",
        "weekday-evening",
        "saturday",
        "sunday",
    ],
)
def test_is_market_open(mock_time, expected):
    with patch("optionctl.cache.datetime") as mock_dt:
        mock_dt.now.return_value = mock_time
        assert _is_market_open() is expected


# ---------------------------------------------------------------------------
# _is_cache_valid tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current_time", "cached_time", "expected"),
    [
        # During market hours - 5 minute TTL
        # 10:00 AM ET = 15:00 UTC (EST is UTC-5)
        (
            datetime(2026, 1, 28, 10, 0, tzinfo=_ET),  # current: Wed 10am ET
            datetime(2026, 1, 28, 14, 57, tzinfo=UTC),  # cached: 3 min ago (14:57 UTC)
            True,
        ),
        (
            datetime(2026, 1, 28, 10, 0, tzinfo=_ET),  # current: Wed 10am ET
            datetime(2026, 1, 28, 14, 50, tzinfo=UTC),  # cached: 10 min ago (14:50 UTC)
            False,
        ),
        # After hours on same day - valid if cached after 4pm
        (
            datetime(2026, 1, 28, 20, 0, tzinfo=_ET),  # current: Wed 8pm
            datetime(2026, 1, 28, 21, 0, tzinfo=UTC),  # cached: Wed ~4pm ET
            True,
        ),
        # Weekend - valid if cached Friday after close
        (
            datetime(2026, 1, 31, 12, 0, tzinfo=_ET),  # current: Sat noon
            datetime(2026, 1, 30, 21, 30, tzinfo=UTC),  # cached: Fri ~4:30pm ET
            True,
        ),
        # Weekend - invalid if cached before Friday close
        (
            datetime(2026, 1, 31, 12, 0, tzinfo=_ET),  # current: Sat noon
            datetime(2026, 1, 30, 18, 0, tzinfo=UTC),  # cached: Fri ~1pm ET
            False,
        ),
    ],
    ids=[
        "market-hours-fresh",
        "market-hours-stale",
        "after-hours-valid",
        "weekend-friday-cache",
        "weekend-stale",
    ],
)
def test_is_cache_valid(current_time, cached_time, expected):
    with (
        patch("optionctl.cache._is_market_open") as mock_market,
        patch("optionctl.cache.datetime") as mock_dt,
    ):
        # Determine if market would be open at current_time
        is_market = current_time.weekday() < 5 and current_time.hour >= 9 and current_time.hour < 16
        mock_market.return_value = is_market
        mock_dt.now.side_effect = (
            lambda tz=None: current_time if tz == _ET else current_time.astimezone(UTC)
        )

        assert _is_cache_valid(cached_time) is expected


# ---------------------------------------------------------------------------
# write_chain_cache / read_chain_cache tests
# ---------------------------------------------------------------------------


def test_write_and_read_chain_cache(cache_dir, sample_chain_df):
    """Write cache and read it back."""
    chains = {"2026-01-30": sample_chain_df}

    write_chain_cache(
        ticker="AAPL",
        underlying_price=150.0,
        expirations=["2026-01-30"],
        chains=chains,
        days_to_earnings=5,
    )

    # Verify file exists
    cache_file = cache_dir / "AAPL.json"
    assert cache_file.exists()

    # Read raw to verify structure
    data = json.loads(cache_file.read_text())
    assert data["ticker"] == "AAPL"
    assert data["underlying_price"] == 150.0
    assert data["expirations"] == ["2026-01-30"]
    assert data["days_to_earnings"] == 5
    assert "2026-01-30" in data["chains"]
    assert len(data["chains"]["2026-01-30"]) == 2


@pytest.mark.usefixtures("cache_dir")
def test_read_chain_cache_valid(sample_chain_df):
    """Read valid (fresh) cache."""
    chains = {"2026-01-30": sample_chain_df}
    write_chain_cache("TEST", 100.0, ["2026-01-30"], chains)

    with patch("optionctl.cache._is_cache_valid", return_value=True):
        result = read_chain_cache("test")  # lowercase should work

    assert result is not None
    assert result["ticker"] == "TEST"
    assert result["underlying_price"] == 100.0


@pytest.mark.usefixtures("cache_dir")
def test_read_chain_cache_expired(sample_chain_df):
    """Expired cache returns None."""
    chains = {"2026-01-30": sample_chain_df}
    write_chain_cache("TEST", 100.0, ["2026-01-30"], chains)

    with patch("optionctl.cache._is_cache_valid", return_value=False):
        result = read_chain_cache("TEST")

    assert result is None


@pytest.mark.usefixtures("cache_dir")
def test_read_chain_cache_missing():
    """Missing cache file returns None."""
    result = read_chain_cache("NOTCACHED")
    assert result is None


def test_read_chain_cache_corrupt(cache_dir):
    """Corrupt cache file returns None."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "CORRUPT.json").write_text("not valid json{{{")

    result = read_chain_cache("CORRUPT")
    assert result is None


def test_read_chain_cache_missing_timestamp(cache_dir):
    """Cache without timestamp returns None."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "NOTIME.json").write_text('{"ticker": "NOTIME"}')

    result = read_chain_cache("NOTIME")
    assert result is None


def test_write_chain_cache_ticker_uppercase(cache_dir, sample_chain_df):
    """Ticker is stored uppercase."""
    write_chain_cache("aapl", 150.0, ["2026-01-30"], {"2026-01-30": sample_chain_df})

    assert (cache_dir / "AAPL.json").exists()
    data = json.loads((cache_dir / "AAPL.json").read_text())
    assert data["ticker"] == "AAPL"


def test_write_chain_cache_no_earnings(cache_dir, sample_chain_df):
    """Cache can be written without earnings data."""
    write_chain_cache("TEST", 100.0, ["2026-01-30"], {"2026-01-30": sample_chain_df})

    data = json.loads((cache_dir / "TEST.json").read_text())
    assert data["days_to_earnings"] is None


def test_write_chain_cache_handles_timestamps(cache_dir):
    """DataFrame with pandas Timestamps can be serialized."""
    df = pd.DataFrame(
        {
            "strike": [100.0],
            "lastTradeDate": [pd.Timestamp("2026-01-28 10:00:00")],
        }
    )
    # Should not raise
    write_chain_cache("TSTEST", 100.0, ["2026-01-30"], {"2026-01-30": df})

    data = json.loads((cache_dir / "TSTEST.json").read_text())
    assert "2026-01-30" in data["chains"]


# ---------------------------------------------------------------------------
# clear_cache tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("cache_dir")
def test_clear_cache_empty():
    """Clear on non-existent directory returns 0."""
    assert clear_cache() == 0


def test_clear_cache_with_files(cache_dir, sample_chain_df):
    """Clear removes all cache files."""
    write_chain_cache("AAPL", 150.0, ["2026-01-30"], {"2026-01-30": sample_chain_df})
    write_chain_cache("MSFT", 400.0, ["2026-01-30"], {"2026-01-30": sample_chain_df})

    count = clear_cache()
    assert count == 2
    assert not list(cache_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# get_cache_stats tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("cache_dir")
def test_get_cache_stats_empty():
    """Stats on empty cache."""
    stats = get_cache_stats()
    assert stats["count"] == 0
    assert stats["size_mb"] == 0.0
    assert stats["tickers"] == []


@pytest.mark.usefixtures("cache_dir")
def test_get_cache_stats_with_files(sample_chain_df):
    """Stats with cached files."""
    write_chain_cache("AAPL", 150.0, ["2026-01-30"], {"2026-01-30": sample_chain_df})
    write_chain_cache("MSFT", 400.0, ["2026-01-30"], {"2026-01-30": sample_chain_df})

    stats = get_cache_stats()
    assert stats["count"] == 2
    assert stats["size_mb"] >= 0.0
    assert sorted(stats["tickers"]) == ["AAPL", "MSFT"]
