"""Tests for the scanner module."""

from __future__ import annotations

from datetime import date
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pandas as pd

from optionctl.models import OptionCandidate, ScoringWeights
from optionctl.scanner import _parse_expiration, scan_ticker, scan_universe


def test_parse_expiration() -> None:
    result = _parse_expiration("2026-02-14")
    assert result == date(2026, 2, 14)


def _make_calls_df(
    strikes: list[float],
    asks: list[float],
    volumes: list[int],
    open_interests: list[int],
) -> pd.DataFrame:
    """Build a calls DataFrame mimicking yfinance option_chain().calls."""
    return pd.DataFrame(
        {
            "strike": strikes,
            "ask": asks,
            "bid": [0.0] * len(strikes),
            "lastPrice": asks,
            "volume": volumes,
            "openInterest": open_interests,
            "impliedVolatility": [0.5] * len(strikes),
            "inTheMoney": [False] * len(strikes),
            "contractSymbol": [f"SYM{int(s)}" for s in strikes],
        }
    )


class OptionChain(NamedTuple):
    calls: pd.DataFrame
    puts: pd.DataFrame


def _mock_ticker_with_options(
    underlying_price: float,
    expirations: tuple[str, ...],
    calls_by_exp: dict[str, pd.DataFrame],
) -> MagicMock:
    """Create a mock yf.Ticker with options data."""
    mock = MagicMock()
    mock.options = expirations
    mock.fast_info.last_price = underlying_price

    def option_chain(exp: str) -> OptionChain:
        return OptionChain(calls=calls_by_exp[exp], puts=pd.DataFrame())

    mock.option_chain = option_chain
    return mock


@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_returns_candidates(mock_yf: MagicMock, mock_dt: MagicMock) -> None:
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)

    exp = "2026-01-30"
    calls = _make_calls_df(
        strikes=[200.0, 210.0],
        asks=[0.01, 0.01],
        volumes=[500, 200],
        open_interests=[100, 300],
    )
    mock_yf.Ticker.return_value = _mock_ticker_with_options(
        underlying_price=150.0,
        expirations=(exp,),
        calls_by_exp={exp: calls},
    )

    result = scan_ticker("TEST", min_dte=0, max_dte=14, max_price=0.01, min_volume=100)
    assert len(result) == 2
    assert result[0].ticker == "TEST"
    assert result[0].strike == 200.0
    assert result[0].dte == 3


@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_filters_by_dte(mock_yf: MagicMock, mock_dt: MagicMock) -> None:
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)

    # Expiration is 20 days out, max_dte=14 should exclude it
    exp = "2026-02-16"
    calls = _make_calls_df(
        strikes=[200.0],
        asks=[0.01],
        volumes=[500],
        open_interests=[100],
    )
    mock_yf.Ticker.return_value = _mock_ticker_with_options(
        underlying_price=150.0,
        expirations=(exp,),
        calls_by_exp={exp: calls},
    )

    result = scan_ticker("TEST", min_dte=0, max_dte=14)
    assert len(result) == 0


@patch("optionctl.scanner.yf")
def test_scan_ticker_handles_fetch_error(mock_yf: MagicMock) -> None:
    mock_yf.Ticker.side_effect = RuntimeError("Network error")
    result = scan_ticker("FAIL")
    assert result == []


@patch("optionctl.scanner.yf")
def test_scan_ticker_no_expirations(mock_yf: MagicMock) -> None:
    mock = MagicMock()
    mock.options = ()
    mock_yf.Ticker.return_value = mock
    result = scan_ticker("EMPTY")
    assert result == []


@patch("optionctl.scanner.yf")
def test_scan_ticker_price_fetch_fails(mock_yf: MagicMock) -> None:
    mock = MagicMock()
    mock.options = ("2026-01-30",)
    type(mock.fast_info).last_price = property(
        lambda _: (_ for _ in ()).throw(RuntimeError("no price")),
    )
    mock_yf.Ticker.return_value = mock
    result = scan_ticker("NOPRICE")
    assert result == []


@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_chain_fetch_fails(mock_yf: MagicMock, mock_dt: MagicMock) -> None:
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)

    mock = MagicMock()
    mock.options = ("2026-01-30",)
    mock.fast_info.last_price = 150.0
    mock.option_chain.side_effect = RuntimeError("Chain error")
    mock_yf.Ticker.return_value = mock

    result = scan_ticker("CHAINFAIL")
    assert result == []


@patch("optionctl.scanner.scan_ticker")
def test_scan_universe_aggregates(mock_scan: MagicMock) -> None:
    c1 = OptionCandidate(
        ticker="A",
        strike=100.0,
        expiration=date(2026, 1, 30),
        contract_type="call",
        bid=0.0,
        ask=0.01,
        last_price=0.01,
        volume=500,
        open_interest=100,
        implied_volatility=0.5,
        underlying_price=80.0,
        dte=3,
        volume_oi_ratio=5.0,
        proximity_pct=25.0,
    )
    c2 = OptionCandidate(
        ticker="B",
        strike=200.0,
        expiration=date(2026, 1, 30),
        contract_type="call",
        bid=0.0,
        ask=0.01,
        last_price=0.01,
        volume=300,
        open_interest=50,
        implied_volatility=0.8,
        underlying_price=160.0,
        dte=3,
        volume_oi_ratio=6.0,
        proximity_pct=25.0,
    )

    mock_scan.side_effect = [[c1], [c2], []]

    progress_calls: list[tuple[str, int, int]] = []
    result = scan_universe(
        ["A", "B", "C"],
        progress_callback=lambda t, i, n: progress_calls.append((t, i, n)),
    )

    assert result.tickers_scanned == 3
    assert result.tickers_with_options == 2
    assert len(result.candidates) == 2
    assert len(progress_calls) == 3


@patch("optionctl.scanner.scan_ticker")
def test_scan_universe_with_custom_weights(mock_scan: MagicMock) -> None:
    mock_scan.return_value = []
    weights = ScoringWeights(vol_oi=0, volume=100, proximity=0, iv=0)
    result = scan_universe(["X"], weights=weights)
    assert result.tickers_scanned == 1
    assert result.candidates == []
