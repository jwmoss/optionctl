"""Tests for the Polygon.io data source."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from optionctl.polygon import PolygonSource, _get_api_key, _is_itm, _map_contract

# ---------------------------------------------------------------------------
# _get_api_key
# ---------------------------------------------------------------------------


def test_get_api_key_success(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "test-key-123")
    assert _get_api_key() == "test-key-123"


def test_get_api_key_missing(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="POLYGON_API_KEY"):
        _get_api_key()


# ---------------------------------------------------------------------------
# _is_itm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("contract_type", "strike", "price", "expected"),
    [
        ("call", 100.0, 150.0, True),
        ("call", 200.0, 150.0, False),
        ("put", 200.0, 150.0, True),
        ("put", 100.0, 150.0, False),
        ("call", 100.0, 0.0, False),
    ],
    ids=["call-itm", "call-otm", "put-itm", "put-otm", "zero-price"],
)
def test_is_itm(contract_type, strike, price, expected):
    assert _is_itm(contract_type, strike, price) is expected


# ---------------------------------------------------------------------------
# _map_contract
# ---------------------------------------------------------------------------


def test_map_contract_basic(mock_polygon_response):
    response = mock_polygon_response()
    raw = response["results"][0]
    result = _map_contract(raw)

    assert result["strike"] == 200.0
    assert result["ask"] == 0.01
    assert result["bid"] == 0.0
    assert result["volume"] == 500
    assert result["openInterest"] == 100
    assert result["impliedVolatility"] == 0.5
    assert result["delta"] == 0.05
    assert "contractSymbol" in result


# ---------------------------------------------------------------------------
# PolygonSource
# ---------------------------------------------------------------------------


@patch("optionctl.polygon._get_api_key", return_value="test-key")
def test_polygon_source_init(_mock_key):
    source = PolygonSource()
    assert source._api_key == "test-key"


@patch("optionctl.polygon.write_chain_cache")
@patch("optionctl.polygon.write_no_options_cache")
@patch("optionctl.polygon._get_api_key", return_value="test-key")
def test_polygon_source_fetch_empty_results(_mock_key, mock_no_opts, _mock_cache):
    source = PolygonSource()
    source._last_request_time = 0.0

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [], "status": "OK"}
    mock_resp.raise_for_status = MagicMock()

    with patch("optionctl.polygon.httpx.Client") as mock_client:
        mock_client.return_value.__enter__ = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=mock_resp))
        )
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = source.fetch_ticker_data("EMPTY")

    assert result is None
    mock_no_opts.assert_called_once_with("EMPTY")


@patch("optionctl.polygon.time.sleep")
@patch("optionctl.polygon.time.monotonic")
@patch("optionctl.polygon._get_api_key", return_value="test-key")
def test_polygon_source_rate_limiting(_mock_key, mock_monotonic, mock_sleep):
    source = PolygonSource()
    source._last_request_time = 100.0
    mock_monotonic.return_value = 105.0  # 5 seconds elapsed

    source._rate_limit()

    mock_sleep.assert_called_once()
    delay = mock_sleep.call_args[0][0]
    assert delay == pytest.approx(7.0, abs=0.1)


@patch("optionctl.polygon._get_api_key", return_value="test-key")
def test_polygon_source_api_error(_mock_key):
    import httpx

    source = PolygonSource()
    source._last_request_time = 0.0

    with patch("optionctl.polygon.httpx.Client") as mock_client:
        mock_get = MagicMock(side_effect=httpx.HTTPError("timeout"))
        mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(get=mock_get))
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = source._fetch_snapshot("FAIL")

    assert result is None


@patch("optionctl.polygon.write_chain_cache")
@patch("optionctl.polygon._get_api_key", return_value="test-key")
def test_polygon_source_filters_by_dte(_mock_key, _mock_cache, mock_polygon_response):
    source = PolygonSource()
    source._last_request_time = 0.0

    contracts = [
        {
            "details": {
                "ticker": "O:TEST260130C00200000",
                "contract_type": "call",
                "strike_price": 200.0,
                "expiration_date": "2099-01-30",
            },
            "day": {"volume": 500, "close": 0.01},
            "open_interest": 100,
            "implied_volatility": 0.5,
            "last_quote": {"bid": 0.0, "ask": 0.01},
            "underlying_asset": {"price": 150.0},
            "greeks": {"delta": 0.05},
        },
    ]
    response = mock_polygon_response(contracts=contracts)

    mock_resp = MagicMock()
    mock_resp.json.return_value = response
    mock_resp.raise_for_status = MagicMock()

    with patch("optionctl.polygon.httpx.Client") as mock_client:
        mock_client.return_value.__enter__ = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=mock_resp))
        )
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        result = source.fetch_ticker_data("TEST", max_dte=14)

    assert result is None
