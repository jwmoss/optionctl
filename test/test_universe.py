"""Tests for the universe module."""

from unittest.mock import patch

import pandas as pd

from optionctl.universe import _read_ticker_cache, _write_ticker_cache, get_sp500_tickers


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
    assert _read_ticker_cache("sp500") == ["NVDA", "TSLA"]
