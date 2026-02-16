"""Tests for the scanner module."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from optionctl.models import ScoringWeights, Side
from optionctl.scanner import _parse_expiration, scan_ticker, scan_universe


def test_parse_expiration():
    assert _parse_expiration("2026-02-14") == date(2026, 2, 14)


# ---------------------------------------------------------------------------
# scan_ticker
# ---------------------------------------------------------------------------


@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_returns_candidates(
    mock_yf, mock_dt, _mock_record, _mock_vol, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-01-30"
    calls = make_calls_df(
        strikes=[200.0, 210.0], asks=[0.01, 0.01], volumes=[500, 200], open_interests=[100, 300]
    )
    mock_yf.Ticker.return_value = make_mock_ticker(150.0, (exp,), {exp: calls})

    result = scan_ticker(
        "TEST", min_dte=0, max_dte=14, max_price=0.01, min_volume=100, use_cache=False
    )
    assert len(result) == 2
    assert result[0].ticker == "TEST"
    assert result[0].strike == 200.0
    assert result[0].dte == 3
    assert result[0].contract_type == "call"


@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_puts(
    mock_yf, mock_dt, _mock_record, _mock_vol, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-01-30"
    calls = make_calls_df(strikes=[200.0])
    puts = make_calls_df(strikes=[80.0, 70.0])
    mock_yf.Ticker.return_value = make_mock_ticker(
        150.0, (exp,), {exp: calls}, puts_by_exp={exp: puts}
    )

    result = scan_ticker("TEST", side=Side.PUTS, use_cache=False)
    assert len(result) == 2
    assert all(c.contract_type == "put" for c in result)


@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_both_sides(
    mock_yf, mock_dt, _mock_record, _mock_vol, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-01-30"
    calls = make_calls_df(strikes=[200.0])
    puts = make_calls_df(strikes=[80.0])
    mock_yf.Ticker.return_value = make_mock_ticker(
        150.0, (exp,), {exp: calls}, puts_by_exp={exp: puts}
    )

    result = scan_ticker("TEST", side=Side.BOTH, use_cache=False)
    types = {c.contract_type for c in result}
    assert "call" in types
    assert "put" in types


@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_default_is_calls(
    mock_yf, mock_dt, _mock_record, _mock_vol, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-01-30"
    calls = make_calls_df(strikes=[200.0])
    puts = make_calls_df(strikes=[80.0])
    mock_yf.Ticker.return_value = make_mock_ticker(
        150.0, (exp,), {exp: calls}, puts_by_exp={exp: puts}
    )

    result = scan_ticker("TEST", use_cache=False)
    assert all(c.contract_type == "call" for c in result)


@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_filters_by_dte(
    mock_yf, mock_dt, _mock_record, _mock_vol, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-02-16"  # 20 days out
    calls = make_calls_df(strikes=[200.0])
    mock_yf.Ticker.return_value = make_mock_ticker(150.0, (exp,), {exp: calls})

    result = scan_ticker("TEST", min_dte=0, max_dte=14, use_cache=False)
    assert len(result) == 0


@pytest.mark.parametrize(
    ("setup", "ticker"),
    [
        ("fetch_error", "FAIL"),
        ("no_expirations", "EMPTY"),
        ("no_price", "NOPRICE"),
        ("chain_error", "CHAINFAIL"),
    ],
)
@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_error_scenarios(mock_yf, mock_dt, _mock_record, _mock_vol, setup, ticker):
    """All error paths should return an empty list, never raise."""
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)

    if setup == "fetch_error":
        mock_yf.Ticker.side_effect = RuntimeError("Network error")
    elif setup == "no_expirations":
        mock_yf.Ticker.return_value.options = ()
    elif setup == "no_price":
        mock = MagicMock()
        mock.options = ("2026-01-30",)
        type(mock.fast_info).last_price = property(
            lambda _: (_ for _ in ()).throw(RuntimeError("no price")),
        )
        mock_yf.Ticker.return_value = mock
    elif setup == "chain_error":
        mock = MagicMock()
        mock.options = ("2026-01-30",)
        mock.fast_info.last_price = 150.0
        mock.option_chain.side_effect = RuntimeError("Chain error")
        mock_yf.Ticker.return_value = mock

    assert scan_ticker(ticker, use_cache=False) == []


@patch("optionctl.scanner.compute_vol_vs_avg", return_value=None)
@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.datetime")
@patch("optionctl.scanner.yf")
def test_scan_ticker_with_source(mock_yf, mock_dt, _mock_record, _mock_vol, make_calls_df):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    source = MagicMock()
    source.fetch_ticker_data.return_value = {
        "ticker": "SRC",
        "underlying_price": 100.0,
        "expirations": ["2026-01-30"],
        "chains": {
            "2026-01-30": {
                "calls": make_calls_df(strikes=[120.0]).to_dict(orient="records"),
                "puts": [],
            }
        },
        "days_to_earnings": None,
    }

    result = scan_ticker("SRC", use_cache=False, source=source)
    assert len(result) == 1
    source.fetch_ticker_data.assert_called_once()


# ---------------------------------------------------------------------------
# scan_universe
# ---------------------------------------------------------------------------


@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.scan_ticker")
def test_scan_universe_aggregates(mock_scan, _mock_record, make_candidate):
    c1 = make_candidate(ticker="A", strike=100.0)
    c2 = make_candidate(
        ticker="B", strike=200.0, underlying_price=160.0, implied_volatility=0.8, open_interest=50
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


@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.scan_ticker")
def test_scan_universe_with_custom_weights(mock_scan, _mock_record):
    mock_scan.return_value = []
    weights = ScoringWeights(vol_oi=0, volume=100, proximity=0, iv=0)
    result = scan_universe(["X"], weights=weights)
    assert result.tickers_scanned == 1
    assert result.candidates == []


@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.scan_ticker")
def test_scan_universe_threads_side(mock_scan, _mock_record):
    mock_scan.return_value = []
    scan_universe(["X"], side=Side.PUTS)
    _, kwargs = mock_scan.call_args
    assert kwargs["side"] == Side.PUTS


@patch("optionctl.scanner.record_volume_snapshot")
@patch("optionctl.scanner.scan_ticker")
def test_scan_universe_threads_source(mock_scan, _mock_record):
    mock_scan.return_value = []
    source = MagicMock()
    scan_universe(["X"], source=source)
    _, kwargs = mock_scan.call_args
    assert kwargs["source"] is source
