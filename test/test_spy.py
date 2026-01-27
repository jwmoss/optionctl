"""Tests for the SPY 0DTE module."""

from __future__ import annotations

from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pandas as pd

from optionctl.models import ScoringWeights
from optionctl.spy import (
    _get_spy_0dte_expiration,
    _get_spy_price,
    find_momentum_0dte,
    find_penny_0dte,
)


class OptionChain(NamedTuple):
    calls: pd.DataFrame
    puts: pd.DataFrame


def _make_spy_calls(
    strikes: list[float],
    asks: list[float],
    volumes: list[int],
    open_interests: list[int],
    in_the_money: list[bool] | None = None,
) -> pd.DataFrame:
    n = len(strikes)
    return pd.DataFrame(
        {
            "strike": strikes,
            "ask": asks,
            "bid": [0.0] * n,
            "lastPrice": asks,
            "volume": volumes,
            "openInterest": open_interests,
            "impliedVolatility": [0.5] * n,
            "inTheMoney": in_the_money or [False] * n,
            "contractSymbol": [f"SPY{int(s)}" for s in strikes],
        }
    )


@patch("optionctl.spy.datetime")
@patch("optionctl.spy.yf")
def test_get_spy_0dte_expiration_found(mock_yf: MagicMock, mock_dt: MagicMock) -> None:
    mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-27"
    mock_yf.Ticker.return_value.options = ("2026-01-26", "2026-01-27", "2026-01-28")
    assert _get_spy_0dte_expiration() == "2026-01-27"


@patch("optionctl.spy.datetime")
@patch("optionctl.spy.yf")
def test_get_spy_0dte_expiration_not_found(mock_yf: MagicMock, mock_dt: MagicMock) -> None:
    mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-01-28"
    mock_yf.Ticker.return_value.options = ("2026-01-26", "2026-01-27", "2026-01-30")
    assert _get_spy_0dte_expiration() is None


@patch("optionctl.spy.yf")
def test_get_spy_0dte_expiration_fetch_error(mock_yf: MagicMock) -> None:
    mock_yf.Ticker.side_effect = RuntimeError("network")
    assert _get_spy_0dte_expiration() is None


@patch("optionctl.spy.yf")
def test_get_spy_price_success(mock_yf: MagicMock) -> None:
    mock_yf.Ticker.return_value.fast_info.last_price = 600.0
    assert _get_spy_price() == 600.0


@patch("optionctl.spy.yf")
def test_get_spy_price_failure(mock_yf: MagicMock) -> None:
    type(mock_yf.Ticker.return_value.fast_info).last_price = property(
        lambda _: (_ for _ in ()).throw(RuntimeError("no price")),
    )
    import pytest

    with pytest.raises(RuntimeError, match="Failed to get SPY price"):
        _get_spy_price()


@patch("optionctl.spy._get_spy_0dte_expiration", return_value=None)
def test_find_penny_0dte_no_expiration(_mock: MagicMock) -> None:
    assert find_penny_0dte() == []


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_with_results(
    _mock_exp: MagicMock, _mock_price: MagicMock, mock_yf: MagicMock
) -> None:
    calls = _make_spy_calls(
        strikes=[620.0, 630.0],
        asks=[0.01, 0.01],
        volumes=[500, 300],
        open_interests=[100, 200],
    )
    mock_yf.Ticker.return_value.option_chain.return_value = OptionChain(
        calls=calls, puts=pd.DataFrame()
    )

    result = find_penny_0dte(max_price=0.01, min_volume=100)
    assert len(result) == 2
    assert all(c.ticker == "SPY" for c in result)
    assert all(c.dte == 0 for c in result)


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_chain_error(
    _mock_exp: MagicMock, _mock_price: MagicMock, mock_yf: MagicMock
) -> None:
    mock_yf.Ticker.return_value.option_chain.side_effect = RuntimeError("chain fail")
    result = find_penny_0dte()
    assert result == []


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_penny_0dte_custom_weights(
    _mock_exp: MagicMock, _mock_price: MagicMock, mock_yf: MagicMock
) -> None:
    calls = _make_spy_calls(
        strikes=[620.0],
        asks=[0.01],
        volumes=[500],
        open_interests=[100],
    )
    mock_yf.Ticker.return_value.option_chain.return_value = OptionChain(
        calls=calls, puts=pd.DataFrame()
    )
    weights = ScoringWeights(vol_oi=0, volume=100, proximity=0, iv=0)
    result = find_penny_0dte(weights=weights)
    assert len(result) == 1


@patch("optionctl.spy._get_spy_0dte_expiration", return_value=None)
def test_find_momentum_0dte_no_expiration(_mock: MagicMock) -> None:
    assert find_momentum_0dte() == []


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_momentum_0dte_with_results(
    _mock_exp: MagicMock, _mock_price: MagicMock, mock_yf: MagicMock
) -> None:
    # Strike 605 is ~0.83% OTM, 610 is ~1.67% OTM (both within default 2%)
    # Strike 650 is ~8.3% OTM (excluded)
    calls = _make_spy_calls(
        strikes=[605.0, 610.0, 650.0],
        asks=[2.50, 1.00, 0.01],
        volumes=[2000, 1500, 800],
        open_interests=[500, 300, 100],
    )
    mock_yf.Ticker.return_value.option_chain.return_value = OptionChain(
        calls=calls, puts=pd.DataFrame()
    )

    result = find_momentum_0dte(max_distance_pct=2.0, min_volume=500)
    assert len(result) == 2
    assert all(c.proximity_pct <= 2.0 for c in result)


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_momentum_0dte_chain_error(
    _mock_exp: MagicMock, _mock_price: MagicMock, mock_yf: MagicMock
) -> None:
    mock_yf.Ticker.return_value.option_chain.side_effect = RuntimeError("chain fail")
    result = find_momentum_0dte()
    assert result == []


@patch("optionctl.spy.yf")
@patch("optionctl.spy._get_spy_price", return_value=600.0)
@patch("optionctl.spy._get_spy_0dte_expiration", return_value="2026-01-27")
def test_find_momentum_0dte_excludes_itm(
    _mock_exp: MagicMock, _mock_price: MagicMock, mock_yf: MagicMock
) -> None:
    # Strike 595 is below current price (ITM), should be excluded
    calls = _make_spy_calls(
        strikes=[595.0, 605.0],
        asks=[5.00, 2.50],
        volumes=[2000, 1500],
        open_interests=[500, 300],
    )
    mock_yf.Ticker.return_value.option_chain.return_value = OptionChain(
        calls=calls, puts=pd.DataFrame()
    )

    result = find_momentum_0dte(max_distance_pct=2.0, min_volume=500)
    assert len(result) == 1
    assert result[0].strike == 605.0
