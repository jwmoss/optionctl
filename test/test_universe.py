"""Tests for the universe module."""

from pathlib import Path

import pytest

from optionctl.universe import (
    HIGH_VOLUME_TICKERS,
    get_tickers,
    get_top_volume_tickers,
    load_watchlist,
)


def test_get_top_volume_tickers_default() -> None:
    tickers = get_top_volume_tickers()
    assert len(tickers) == 50
    assert "AAPL" in tickers
    assert "NVDA" in tickers


def test_get_top_volume_tickers_limited() -> None:
    tickers = get_top_volume_tickers(5)
    assert len(tickers) == 5


def test_get_top_volume_tickers_exceeds_list() -> None:
    tickers = get_top_volume_tickers(1000)
    assert len(tickers) == len(HIGH_VOLUME_TICKERS)


def test_load_watchlist(tmp_path: Path) -> None:
    p = tmp_path / "tickers.txt"
    p.write_text("AAPL\nMSFT\n# comment\n\nTSLA\n")
    tickers = load_watchlist(p)
    assert tickers == ["AAPL", "MSFT", "TSLA"]


def test_load_watchlist_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_watchlist("/nonexistent/path/tickers.txt")


def test_load_watchlist_lowercased(tmp_path: Path) -> None:
    p = tmp_path / "tickers.txt"
    p.write_text("aapl\nmsft\n")
    tickers = load_watchlist(p)
    assert tickers == ["AAPL", "MSFT"]


def test_get_tickers_volume() -> None:
    tickers = get_tickers("volume", top_n=5)
    assert len(tickers) == 5


def test_get_tickers_watchlist_no_file() -> None:
    with pytest.raises(ValueError, match="--watchlist-file is required"):
        get_tickers("watchlist")


def test_get_tickers_unknown_universe() -> None:
    with pytest.raises(ValueError, match="Unknown universe"):
        get_tickers("invalid")
