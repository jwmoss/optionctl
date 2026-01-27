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


@dataclass
class ScoringWeights:
    """Configurable weights for composite scoring (must sum to 100)."""

    vol_oi: float = 30.0
    volume: float = 15.0
    proximity: float = 30.0
    iv: float = 25.0


@dataclass
class ScanResult:
    """Result of a scan across multiple tickers."""

    candidates: list[OptionCandidate] = field(default_factory=list)
    tickers_scanned: int = 0
    tickers_with_options: int = 0
    errors: list[str] = field(default_factory=list)
