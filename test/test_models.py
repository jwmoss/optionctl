"""Tests for the models module."""

from datetime import date

from optionctl.models import OptionCandidate, ScanResult, Side


def test_option_candidate_defaults() -> None:
    c = OptionCandidate(
        ticker="AAPL",
        strike=250.0,
        expiration=date(2025, 1, 31),
        contract_type="call",
        bid=0.0,
        ask=0.01,
        last_price=0.01,
        volume=500,
        open_interest=100,
        implied_volatility=0.45,
    )
    assert c.ticker == "AAPL"
    assert c.score == 0.0
    assert c.dte == 0
    assert c.underlying_price == 0.0
    assert c.contract_symbol == ""
    assert c.vol_vs_avg is None
    assert c.delta is None
    assert c.gamma is None
    assert c.theta is None
    assert c.vega is None


def test_scan_result_defaults() -> None:
    r = ScanResult()
    assert r.candidates == []
    assert r.tickers_scanned == 0
    assert r.tickers_with_options == 0
    assert r.errors == []


def test_scan_result_with_candidates() -> None:
    c = OptionCandidate(
        ticker="TSLA",
        strike=300.0,
        expiration=date(2025, 2, 7),
        contract_type="call",
        bid=0.0,
        ask=0.01,
        last_price=0.01,
        volume=1000,
        open_interest=200,
        implied_volatility=0.80,
    )
    r = ScanResult(candidates=[c], tickers_scanned=10, tickers_with_options=1)
    assert len(r.candidates) == 1
    assert r.tickers_scanned == 10


def test_side_enum_values() -> None:
    assert Side.CALLS.value == "calls"
    assert Side.PUTS.value == "puts"
    assert Side.BOTH.value == "both"
    assert Side("calls") == Side.CALLS
