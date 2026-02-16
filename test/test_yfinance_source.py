"""Tests for the YFinance data source extraction."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from optionctl.yfinance_source import YFinanceSource

# ---------------------------------------------------------------------------
# YFinanceSource.fetch_ticker_data
# ---------------------------------------------------------------------------


@patch("optionctl.yfinance_source.write_chain_cache")
@patch("optionctl.yfinance_source.datetime")
@patch("optionctl.yfinance_source.yf")
def test_yfinance_source_fetch_success(
    mock_yf, mock_dt, _mock_cache, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-01-30"
    calls = make_calls_df(strikes=[200.0])
    mock_yf.Ticker.return_value = make_mock_ticker(150.0, (exp,), {exp: calls})

    source = YFinanceSource()
    result = source.fetch_ticker_data("TEST")

    assert result is not None
    assert result["ticker"] == "TEST"
    assert result["underlying_price"] == 150.0
    assert "2026-01-30" in result["chains"]
    assert "calls" in result["chains"]["2026-01-30"]
    assert "puts" in result["chains"]["2026-01-30"]


@patch("optionctl.yfinance_source.write_no_options_cache")
@patch("optionctl.yfinance_source.yf")
def test_yfinance_source_no_options(mock_yf, mock_no_opts):
    mock = MagicMock()
    mock.options = ()
    mock_yf.Ticker.return_value = mock

    source = YFinanceSource()
    result = source.fetch_ticker_data("EMPTY")

    assert result is None
    mock_no_opts.assert_called_once_with("EMPTY")


@patch("optionctl.yfinance_source.yf")
def test_yfinance_source_fetch_error(mock_yf):
    mock_yf.Ticker.side_effect = RuntimeError("API error")

    source = YFinanceSource()
    result = source.fetch_ticker_data("FAIL")

    assert result is None


@patch("optionctl.yfinance_source.write_chain_cache")
@patch("optionctl.yfinance_source.datetime")
@patch("optionctl.yfinance_source.yf")
def test_yfinance_source_no_price(mock_yf, mock_dt, _mock_cache):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    mock = MagicMock()
    mock.options = ("2026-01-30",)
    type(mock.fast_info).last_price = property(
        lambda _: (_ for _ in ()).throw(RuntimeError("no price")),
    )
    mock_yf.Ticker.return_value = mock

    source = YFinanceSource()
    result = source.fetch_ticker_data("NOPRICE")

    assert result is None


@patch("optionctl.yfinance_source.write_chain_cache")
@patch("optionctl.yfinance_source.datetime")
@patch("optionctl.yfinance_source.yf")
def test_yfinance_source_max_dte_zero(
    mock_yf, mock_dt, _mock_cache, make_calls_df, make_mock_ticker
):
    mock_dt.now.return_value.date.return_value = date(2026, 1, 27)
    exp = "2026-06-30"
    calls = make_calls_df(strikes=[200.0])
    mock_yf.Ticker.return_value = make_mock_ticker(150.0, (exp,), {exp: calls})

    source = YFinanceSource()
    result = source.fetch_ticker_data("TEST", max_dte=0)

    assert result is not None
    assert "2026-06-30" in result["chains"]
