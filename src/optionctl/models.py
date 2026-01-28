"""Data models for optionctl."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


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
    delta: float = 0.0
    volume_vs_avg: float = 0.0  # today's volume as multiple of average
    days_to_earnings: int | None = None  # days until next earnings, None if unknown


@dataclass
class ScoringWeights:
    """Configurable weights for composite scoring."""

    vol_oi: float = 25.0
    volume: float = 10.0
    proximity: float = 25.0
    iv: float = 20.0
    # Enhanced signal weights
    delta: float = 10.0
    unusual_volume: float = 10.0
    earnings: float = 0.0  # disabled by default, enable with --w-earnings


@dataclass
class ScanResult:
    """Result of a scan across multiple tickers."""

    candidates: list[OptionCandidate] = field(default_factory=list)
    tickers_scanned: int = 0
    tickers_with_options: int = 0
    errors: list[str] = field(default_factory=list)
