"""Shared fixtures for optionctl tests.

Follows the datasette-enrichments pattern: heavy conftest with reusable
factories so individual test files stay focused on assertions.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple
from unittest.mock import MagicMock

import pandas as pd
import pytest

from optionctl.models import OptionCandidate, ScoringWeights

# ---------------------------------------------------------------------------
# DataFrame factories (mimic yfinance structures)
# ---------------------------------------------------------------------------


class OptionChain(NamedTuple):
    """Lightweight stand-in for ``yf.Ticker.option_chain()``."""

    calls: pd.DataFrame
    puts: pd.DataFrame


@pytest.fixture
def make_calls_df():
    """Factory fixture: build a calls DataFrame mimicking yfinance."""

    def _factory(
        strikes: list[float],
        asks: list[float] | None = None,
        volumes: list[int] | None = None,
        open_interests: list[int] | None = None,
        implied_vols: list[float] | None = None,
        in_the_money: list[bool] | None = None,
    ) -> pd.DataFrame:
        n = len(strikes)
        asks = asks or [0.01] * n
        volumes = volumes or [500] * n
        open_interests = open_interests or [100] * n
        implied_vols = implied_vols or [0.5] * n
        in_the_money = in_the_money or [False] * n
        return pd.DataFrame(
            {
                "strike": strikes,
                "ask": asks,
                "bid": [0.0] * n,
                "lastPrice": asks,
                "volume": volumes,
                "openInterest": open_interests,
                "impliedVolatility": implied_vols,
                "inTheMoney": in_the_money,
                "contractSymbol": [f"SYM{int(s)}" for s in strikes],
            }
        )

    return _factory


@pytest.fixture
def sample_calls_df(make_calls_df):
    """A ready-made calls DataFrame with two OTM penny options."""
    return make_calls_df(
        strikes=[200.0, 210.0],
        asks=[0.01, 0.01],
        volumes=[500, 200],
        open_interests=[100, 300],
    )


# ---------------------------------------------------------------------------
# Mock ticker factory
# ---------------------------------------------------------------------------


@pytest.fixture
def make_mock_ticker():
    """Factory fixture: create a mock ``yf.Ticker`` with options data."""

    def _factory(
        underlying_price: float,
        expirations: tuple[str, ...],
        calls_by_exp: dict[str, pd.DataFrame],
        puts_by_exp: dict[str, pd.DataFrame] | None = None,
    ) -> MagicMock:
        mock = MagicMock()
        mock.options = expirations
        mock.fast_info.last_price = underlying_price

        def option_chain(exp: str) -> OptionChain:
            calls = calls_by_exp[exp]
            puts = puts_by_exp[exp] if puts_by_exp and exp in puts_by_exp else pd.DataFrame()
            return OptionChain(calls=calls, puts=puts)

        mock.option_chain = option_chain
        return mock

    return _factory


# ---------------------------------------------------------------------------
# OptionCandidate factory
# ---------------------------------------------------------------------------


@pytest.fixture
def make_candidate():
    """Factory fixture: build an ``OptionCandidate`` with sensible defaults."""

    def _factory(
        ticker: str = "TEST",
        strike: float = 100.0,
        expiration: date = date(2026, 1, 30),
        contract_type: str = "call",
        volume: int = 500,
        open_interest: int = 100,
        implied_volatility: float = 0.5,
        underlying_price: float = 80.0,
        dte: int = 3,
        volume_oi_ratio: float = 5.0,
        proximity_pct: float = 25.0,
        ask: float = 0.01,
        days_to_earnings: int | None = None,
        vol_vs_avg: float | None = None,
        contract_symbol: str = "",
        delta: float | None = None,
        gamma: float | None = None,
        theta: float | None = None,
        vega: float | None = None,
    ) -> OptionCandidate:
        return OptionCandidate(
            ticker=ticker,
            strike=strike,
            expiration=expiration,
            contract_type=contract_type,
            bid=0.0,
            ask=ask,
            last_price=ask,
            volume=volume,
            open_interest=open_interest,
            implied_volatility=implied_volatility,
            underlying_price=underlying_price,
            dte=dte,
            volume_oi_ratio=volume_oi_ratio,
            proximity_pct=proximity_pct,
            days_to_earnings=days_to_earnings,
            vol_vs_avg=vol_vs_avg,
            contract_symbol=contract_symbol,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
        )

    return _factory


# ---------------------------------------------------------------------------
# Common scoring weight presets
# ---------------------------------------------------------------------------


@pytest.fixture
def default_weights() -> ScoringWeights:
    """Default scoring weights (25/15/25/20/15)."""
    return ScoringWeights(
        vol_oi=25.0,
        volume=15.0,
        proximity=25.0,
        iv=20.0,
        earnings=15.0,
    )


@pytest.fixture
def volume_only_weights() -> ScoringWeights:
    """Only raw volume matters."""
    return ScoringWeights(vol_oi=0.0, volume=100.0, proximity=0.0, iv=0.0, earnings=0.0)


@pytest.fixture
def proximity_only_weights() -> ScoringWeights:
    """Only strike proximity matters."""
    return ScoringWeights(vol_oi=0.0, volume=0.0, proximity=100.0, iv=0.0, earnings=0.0)


# ---------------------------------------------------------------------------
# Watchlist file fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def watchlist_file(tmp_path):
    """Create a temporary watchlist file and return its path."""

    def _factory(content: str = "AAPL\nMSFT\n# comment\n\nTSLA\n") -> str:
        p = tmp_path / "tickers.txt"
        p.write_text(content)
        return str(p)

    return _factory


# ---------------------------------------------------------------------------
# History directory fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    """Use a temporary directory for history tests."""
    test_dir = tmp_path / "history"
    monkeypatch.setattr("optionctl.history._HISTORY_DIR", test_dir)
    return test_dir


# ---------------------------------------------------------------------------
# Polygon mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_polygon_response():
    """Factory for Polygon API snapshot responses."""

    def _factory(
        ticker: str = "TEST",
        underlying_price: float = 150.0,
        contracts: list[dict] | None = None,
    ) -> dict:
        if contracts is None:
            contracts = [
                {
                    "details": {
                        "ticker": f"O:{ticker}260130C00200000",
                        "contract_type": "call",
                        "strike_price": 200.0,
                        "expiration_date": "2026-01-30",
                    },
                    "day": {"volume": 500, "close": 0.01, "open": 0.01},
                    "open_interest": 100,
                    "implied_volatility": 0.5,
                    "last_quote": {"bid": 0.0, "ask": 0.01},
                    "underlying_asset": {"price": underlying_price},
                    "greeks": {"delta": 0.05},
                },
            ]
        return {"results": contracts, "status": "OK"}

    return _factory
