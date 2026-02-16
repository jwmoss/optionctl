"""Data models for optionctl."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

# Default weights (sum to 100)
DEFAULT_WEIGHT_VOL_OI = 25.0
DEFAULT_WEIGHT_VOLUME = 15.0
DEFAULT_WEIGHT_PROXIMITY = 25.0
DEFAULT_WEIGHT_IV = 20.0
DEFAULT_WEIGHT_EARNINGS = 15.0


class Side(StrEnum):
    """Which option side(s) to scan."""

    CALLS = "calls"
    PUTS = "puts"
    BOTH = "both"


@runtime_checkable
class OptionDataSource(Protocol):
    """Protocol for option data providers."""

    def fetch_ticker_data(
        self, ticker: str, *, fetch_enhanced: bool = True, max_dte: int = 15
    ) -> dict | None:
        """Fetch option chain data for a ticker.

        Args:
            ticker: Stock ticker symbol.
            fetch_enhanced: Whether to fetch earnings data.
            max_dte: Maximum days to expiration to fetch (0 for all).

        Returns:
            Dict with chain data, or None on failure.
        """
        ...


@dataclass
class OptionCandidate:
    """A candidate option contract identified by the scanner."""

    ticker: str
    strike: float
    expiration: date
    contract_type: str
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float
    underlying_price: float = 0.0
    dte: int = 0
    volume_oi_ratio: float = 0.0
    proximity_pct: float = 0.0
    score: float = 0.0
    contract_symbol: str = ""
    # Enhanced signals
    days_to_earnings: int | None = None  # days until next earnings, None if unknown
    vol_vs_avg: float | None = None  # current volume vs rolling average
    # Greeks (optional; available from some providers such as Polygon)
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


@dataclass
class ScoringWeights:
    """Configurable weights for composite scoring."""

    vol_oi: float = DEFAULT_WEIGHT_VOL_OI
    volume: float = DEFAULT_WEIGHT_VOLUME
    proximity: float = DEFAULT_WEIGHT_PROXIMITY
    iv: float = DEFAULT_WEIGHT_IV
    # Enhanced signal weights
    earnings: float = DEFAULT_WEIGHT_EARNINGS  # catalyst detection
    vol_vs_avg: float = 0.0  # disabled by default, opt-in


@dataclass
class ScanResult:
    """Result of a scan across multiple tickers."""

    candidates: list[OptionCandidate] = field(default_factory=list)
    tickers_scanned: int = 0
    tickers_with_options: int = 0
    errors: list[str] = field(default_factory=list)
