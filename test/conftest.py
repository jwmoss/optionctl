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
    ) -> MagicMock:
        mock = MagicMock()
        mock.options = expirations
        mock.fast_info.last_price = underlying_price

        def option_chain(exp: str) -> OptionChain:
            return OptionChain(calls=calls_by_exp[exp], puts=pd.DataFrame())

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
        volume: int = 500,
        open_interest: int = 100,
        implied_volatility: float = 0.5,
        underlying_price: float = 80.0,
        dte: int = 3,
        volume_oi_ratio: float = 5.0,
        proximity_pct: float = 25.0,
        ask: float = 0.01,
    ) -> OptionCandidate:
        return OptionCandidate(
            ticker=ticker,
            strike=strike,
            expiration=expiration,
            contract_type="call",
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
        )

    return _factory


# ---------------------------------------------------------------------------
# Common scoring weight presets
# ---------------------------------------------------------------------------


@pytest.fixture
def default_weights() -> ScoringWeights:
    """Default scoring weights (30/15/30/25)."""
    return ScoringWeights(vol_oi=30.0, volume=15.0, proximity=30.0, iv=25.0)


@pytest.fixture
def volume_only_weights() -> ScoringWeights:
    """Only raw volume matters."""
    return ScoringWeights(vol_oi=0.0, volume=100.0, proximity=0.0, iv=0.0)


@pytest.fixture
def proximity_only_weights() -> ScoringWeights:
    """Only strike proximity matters."""
    return ScoringWeights(vol_oi=0.0, volume=0.0, proximity=100.0, iv=0.0)


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
