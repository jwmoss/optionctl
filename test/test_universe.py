"""Tests for the universe module."""

from unittest.mock import patch

import pandas as pd
import pytest

from optionctl.universe import (
    HIGH_VOLUME_TICKERS,
    _read_ticker_cache,
    _write_ticker_cache,
    get_sp500_tickers,
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


# ---------------------------------------------------------------------------
# Ticker cache
# ---------------------------------------------------------------------------


def test_write_and_read_ticker_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)
    _write_ticker_cache("test", ["AAPL", "MSFT"])
    assert _read_ticker_cache("test") == ["AAPL", "MSFT"]


def test_read_ticker_cache_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)
    assert _read_ticker_cache("nonexistent") is None


def test_read_ticker_cache_expired(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)
    _write_ticker_cache("test", ["AAPL"])
    assert _read_ticker_cache("test", ttl=0) is None


def test_read_ticker_cache_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)
    (tmp_path / "bad.json").write_text("not json")
    assert _read_ticker_cache("bad") is None


def test_get_sp500_tickers_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)
    _write_ticker_cache("sp500", ["AAPL", "MSFT", "GOOG"])
    # Should use cache, not hit Wikipedia
    assert get_sp500_tickers() == ["AAPL", "MSFT", "GOOG"]


def test_get_sp500_tickers_bypass_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)
    _write_ticker_cache("sp500", ["STALE"])

    mock_df = pd.DataFrame({"Symbol": ["AAPL", "BRK.B"]})
    with (
        patch("optionctl.universe._fetch_wikipedia_html", return_value="<html></html>"),
        patch("pandas.read_html", return_value=[mock_df]),
    ):
        result = get_sp500_tickers(use_cache=False)

    assert result == ["AAPL", "BRK-B"]


def test_get_sp500_tickers_populates_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("optionctl.universe._CACHE_DIR", tmp_path)

    mock_df = pd.DataFrame({"Symbol": ["NVDA", "TSLA"]})
    with (
        patch("optionctl.universe._fetch_wikipedia_html", return_value="<html></html>"),
        patch("pandas.read_html", return_value=[mock_df]),
    ):
        result = get_sp500_tickers()

    assert result == ["NVDA", "TSLA"]
    # Cache should now be populated
    assert _read_ticker_cache("sp500") == ["NVDA", "TSLA"]
