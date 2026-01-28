"""Tests for the universe module."""

import pytest

from optionctl.universe import (
    HIGH_VOLUME_TICKERS,
    get_tickers,
    get_top_volume_tickers,
    load_watchlist,
)

# ---------------------------------------------------------------------------
# get_top_volume_tickers — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("top_n", "expected_len"),
    [
        (50, 50),
        (5, 5),
        (1000, len(HIGH_VOLUME_TICKERS)),
    ],
    ids=["default", "limited", "exceeds-list"],
)
def test_get_top_volume_tickers(top_n, expected_len):
    tickers = get_top_volume_tickers(top_n)
    assert len(tickers) == expected_len


def test_get_top_volume_tickers_contains_known():
    tickers = get_top_volume_tickers()
    assert "AAPL" in tickers
    assert "NVDA" in tickers


# ---------------------------------------------------------------------------
# load_watchlist — using conftest factory
# ---------------------------------------------------------------------------


def test_load_watchlist(watchlist_file):
    path = watchlist_file("AAPL\nMSFT\n# comment\n\nTSLA\n")
    assert load_watchlist(path) == ["AAPL", "MSFT", "TSLA"]


def test_load_watchlist_lowercased(watchlist_file):
    path = watchlist_file("aapl\nmsft\n")
    assert load_watchlist(path) == ["AAPL", "MSFT"]


def test_load_watchlist_not_found():
    with pytest.raises(FileNotFoundError):
        load_watchlist("/nonexistent/path/tickers.txt")


# ---------------------------------------------------------------------------
# get_tickers
# ---------------------------------------------------------------------------


def test_get_tickers_volume():
    assert len(get_tickers("volume", top_n=5)) == 5


@pytest.mark.parametrize(
    ("universe", "error_match"),
    [
        ("watchlist", "--watchlist-file is required"),
        ("invalid", "Unknown universe"),
    ],
    ids=["watchlist-no-file", "unknown-universe"],
)
def test_get_tickers_errors(universe, error_match):
    with pytest.raises(ValueError, match=error_match):
        get_tickers(universe)
