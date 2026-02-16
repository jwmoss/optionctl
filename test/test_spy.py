"""Tests for the SPY 0DTE module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from optionctl.models import ScoringWeights, Side
from optionctl.spy import _get_spy_0dte_expiration, _get_spy_price, find_penny_0dte

# ---------------------------------------------------------------------------
# _get_spy_0dte_expiration — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "expirations", "expected"),
    [
        ("2026-01-27", ("2026-01-26", "2026-01-27", "2026-01-28"), "2026-01-27"),
        ("2026-01-28", ("2026-01-26", "2026-01-27", "2026-01-30"), None),
    ],
    ids=["found", "not-found"],
)
@patch("optionctl.spy.datetime")
@patch("optionctl.spy.yf")
def test_get_spy_0dte_expiration(mock_yf, mock_dt, today, expirations, expected):
    mock_dt.now.return_value.date.return_value.isoformat.return_value = today
    mock_yf.Ticker.return_value.options = expirations
    assert _get_spy_0dte_expiration() == expected


@patch("optionctl.spy.yf")
def test_get_spy_0dte_expiration_fetch_error(mock_yf):
    mock_yf.Ticker.side_effect = RuntimeError("network")
    assert _get_spy_0dte_expiration() is None


# ---------------------------------------------------------------------------
# _get_spy_price
# ---------------------------------------------------------------------------


@patch("optionctl.spy.yf")
def test_get_spy_price_success(mock_yf):
    mock_yf.Ticker.return_value.fast_info.last_price = 600.0
    assert _get_spy_price() == 600.0


@patch("optionctl.spy.yf")
def test_get_spy_price_failure(mock_yf):
    type(mock_yf.Ticker.return_value.fast_info).last_price = property(
        lambda _: (_ for _ in ()).throw(RuntimeError("no price")),
    )
    with pytest.raises(RuntimeError, match="Failed to get SPY price"):
        _get_spy_price()


# ---------------------------------------------------------------------------
# find_penny_0dte
# ---------------------------------------------------------------------------


@patch("optionctl.spy._get_spy_0dte_expiration", return_value=None)
def test_find_penny_0dte_no_expiration(_mock):
    assert find_penny_0dte() == []


@pytest.mark.parametrize(
    ("strikes", "asks", "volumes", "ois", "expected_count"),
    [
        ([620.0, 630.0], [0.01, 0.01], [500, 300], [100, 200], 2),
        ([620.0], [0.05], [500], [100], 0),
        ([620.0], [0.01], [50], [100], 0),
    ],
    ids=["two-candidates", "ask-too-high", "volume-too-low"],
)
@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_scenarios(
    _mock_exp, _mock_price, mock_yf, strikes, asks, volumes, ois, expected_count, make_calls_df
):
    calls = make_calls_df(strikes=strikes, asks=asks, volumes=volumes, open_interests=ois)
    mock_yf.Ticker.return_value.option_chain.return_value = SimpleNamespace(
        calls=calls,
        puts=make_calls_df(strikes=[]),
    )
    result = find_penny_0dte(max_price=0.01, min_volume=100)
    assert len(result) == expected_count
    assert all(c.ticker == "SPY" for c in result)
    assert all(c.dte == 0 for c in result)


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_chain_error(_mock_exp, _mock_price, mock_yf):
    mock_yf.Ticker.return_value.option_chain.side_effect = RuntimeError("chain fail")
    assert find_penny_0dte() == []


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_custom_weights(_mock_exp, _mock_price, mock_yf, make_calls_df):
    calls = make_calls_df(strikes=[620.0])
    mock_yf.Ticker.return_value.option_chain.return_value = SimpleNamespace(
        calls=calls,
        puts=make_calls_df(strikes=[]),
    )
    weights = ScoringWeights(vol_oi=0, volume=100, proximity=0, iv=0)
    assert len(find_penny_0dte(weights=weights)) == 1


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_puts(_mock_exp, _mock_price, mock_yf, make_calls_df):
    calls = make_calls_df(strikes=[620.0])
    puts = make_calls_df(strikes=[580.0, 570.0])
    mock_yf.Ticker.return_value.option_chain.return_value = SimpleNamespace(calls=calls, puts=puts)
    result = find_penny_0dte(side=Side.PUTS)
    assert all(c.contract_type == "put" for c in result)
    assert len(result) == 2


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_both(_mock_exp, _mock_price, mock_yf, make_calls_df):
    calls = make_calls_df(strikes=[620.0])
    puts = make_calls_df(strikes=[580.0])
    mock_yf.Ticker.return_value.option_chain.return_value = SimpleNamespace(calls=calls, puts=puts)
    result = find_penny_0dte(side=Side.BOTH)
    types = {c.contract_type for c in result}
    assert "call" in types
    assert "put" in types
