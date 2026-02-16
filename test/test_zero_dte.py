"""Tests for zero-DTE ORB helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from optionctl.zero_dte import (
    OrbDirection,
    build_position_plan,
    evaluate_orb_signal,
    fetch_zero_dte_candidates,
    select_directional_zero_dte,
)

_ET = ZoneInfo("America/New_York")


def _bars_from_rows(rows):
    """Build a timezone-aware 1m bars DataFrame."""
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(_ET)
    return df.set_index("ts")


def test_evaluate_orb_signal_waiting_opening_range():
    bars = _bars_from_rows(
        [
            ("2026-02-20 09:30", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:31", 100.0, 100.1, 99.9, 100.0, 900),
            ("2026-02-20 09:32", 100.0, 100.1, 99.9, 100.0, 800),
            ("2026-02-20 09:33", 100.0, 100.1, 99.9, 100.0, 850),
        ]
    )

    signal = evaluate_orb_signal(
        "SPY",
        bars,
        now_et=datetime(2026, 2, 20, 9, 33, tzinfo=_ET),
    )

    assert signal.signal == OrbDirection.WAITING
    assert "Opening range" in signal.reason


def test_evaluate_orb_signal_bullish_breakout_no_rsi_requirement():
    bars = _bars_from_rows(
        [
            ("2026-02-20 09:30", 100.0, 100.3, 99.9, 100.1, 1000),
            ("2026-02-20 09:31", 100.1, 100.2, 99.9, 100.0, 1100),
            ("2026-02-20 09:32", 100.0, 100.2, 99.8, 99.9, 1050),
            ("2026-02-20 09:33", 99.9, 100.1, 99.8, 100.0, 980),
            ("2026-02-20 09:34", 100.0, 100.2, 99.9, 100.0, 1000),
            ("2026-02-20 09:35", 100.0, 100.1, 99.8, 99.9, 930),
            ("2026-02-20 09:36", 99.9, 100.1, 99.8, 99.9, 940),
            ("2026-02-20 09:37", 99.9, 100.1, 99.8, 99.9, 920),
            ("2026-02-20 09:38", 99.9, 100.1, 99.8, 99.9, 910),
            ("2026-02-20 09:39", 99.9, 100.1, 99.8, 99.9, 900),
            ("2026-02-20 09:40", 99.9, 100.1, 99.8, 99.9, 900),
            ("2026-02-20 09:41", 99.9, 100.1, 99.8, 99.9, 900),
            ("2026-02-20 09:42", 99.9, 100.1, 99.8, 99.9, 900),
            ("2026-02-20 09:43", 99.9, 100.1, 99.8, 99.9, 900),
            ("2026-02-20 09:44", 99.9, 100.1, 99.8, 99.9, 900),
            ("2026-02-20 09:45", 99.9, 100.0, 99.8, 99.9, 1300),
            ("2026-02-20 09:46", 99.9, 100.6, 99.9, 100.5, 1500),
            ("2026-02-20 09:47", 100.5, 100.7, 100.3, 100.6, 1400),
        ]
    )

    signal = evaluate_orb_signal(
        "SPY",
        bars,
        now_et=datetime(2026, 2, 20, 9, 47, tzinfo=_ET),
        require_rsi_confirmation=False,
    )

    assert signal.signal == OrbDirection.BULLISH
    assert signal.breakout_time is not None
    assert signal.breakout_price is not None


def test_evaluate_orb_signal_rsi_required_blocks_unconfirmed_breakout():
    bars = _bars_from_rows(
        [
            ("2026-02-20 09:30", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:31", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:32", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:33", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:34", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:35", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:36", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:37", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:38", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:39", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:40", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:41", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:42", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:43", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:44", 100.0, 100.2, 99.8, 100.0, 1000),
            ("2026-02-20 09:45", 100.0, 100.2, 99.9, 100.0, 1200),
            ("2026-02-20 09:46", 100.0, 100.8, 100.0, 100.7, 1800),
        ]
    )

    signal = evaluate_orb_signal(
        "SPY",
        bars,
        now_et=datetime(2026, 2, 20, 9, 46, tzinfo=_ET),
        require_rsi_confirmation=True,
    )

    assert signal.signal == OrbDirection.NO_TRADE
    assert signal.rsi_confirmed is False
    assert "RSI" in signal.reason


def test_select_directional_zero_dte_prefers_delta_band(make_candidate):
    candidates = [
        make_candidate(contract_type="call", dte=0, delta=0.52, volume=1000, proximity_pct=1.0),
        make_candidate(contract_type="call", dte=0, delta=0.72, volume=2000, proximity_pct=0.5),
        make_candidate(contract_type="call", dte=0, delta=None, volume=3000, proximity_pct=0.2),
    ]

    selected = select_directional_zero_dte(candidates, OrbDirection.BULLISH, limit=5)

    assert len(selected) == 1
    assert selected[0].delta == 0.52


def test_build_position_plan():
    plan = build_position_plan(
        account_size=25_000,
        entry_price=1.50,
        risk_pct=1.2,
        stop_loss_pct=50.0,
        target_pct=100.0,
        time_stop="11:30",
        max_trades=3,
    )

    assert plan.max_risk_dollars == 300.0
    assert plan.stop_price == 0.75
    assert plan.target_price == 3.0
    assert plan.risk_per_contract == 75.0
    assert plan.contracts == 4


def test_fetch_zero_dte_candidates_filters_by_dte_price_and_volume(monkeypatch):
    class _MockSource:
        def fetch_ticker_data(self, ticker, *, fetch_enhanced=True, max_dte=15):  # noqa: ARG002
            today_date = datetime.now(tz=_ET).date()
            today = today_date.isoformat()
            tomorrow = (today_date + pd.Timedelta(days=1)).isoformat()
            return {
                "ticker": ticker,
                "underlying_price": 600.0,
                "expirations": [today, tomorrow],
                "chains": {
                    today: {
                        "calls": [
                            {
                                "strike": 599.0,
                                "ask": 1.2,
                                "lastPrice": 1.2,
                                "volume": 500,
                                "openInterest": 200,
                                "inTheMoney": True,
                                "delta": 0.55,
                                "contractSymbol": "CALL0DTE",
                            },
                            {
                                "strike": 610.0,
                                "ask": 6.5,
                                "lastPrice": 6.5,
                                "volume": 900,
                                "openInterest": 500,
                                "inTheMoney": False,
                                "delta": 0.40,
                                "contractSymbol": "CALLTOOEXP",
                            },
                        ],
                        "puts": [],
                    },
                    tomorrow: {
                        "calls": [
                            {
                                "strike": 600.0,
                                "ask": 1.0,
                                "lastPrice": 1.0,
                                "volume": 500,
                                "openInterest": 200,
                                "delta": 0.50,
                                "contractSymbol": "CALL1DTE",
                            }
                        ],
                        "puts": [],
                    },
                },
                "days_to_earnings": None,
            }

    monkeypatch.setattr("optionctl.zero_dte._build_source", lambda _name: _MockSource())

    result = fetch_zero_dte_candidates("SPY", max_price=5.0, min_volume=100)

    assert len(result) == 1
    assert result[0].contract_symbol == "CALL0DTE"
    assert result[0].dte == 0
