"""Utilities for constructing option candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from optionctl.filters import proximity_pct, volume_oi_ratio
from optionctl.models import OptionCandidate

if TYPE_CHECKING:
    from datetime import date

    import pandas as pd


@dataclass(frozen=True)
class CandidateContext:
    """Shared candidate metadata independent of an option-chain row."""

    expiration: date
    underlying_price: float
    dte: int
    days_to_earnings: int | None = None


def build_candidate_from_row(
    *,
    ticker: str,
    row: pd.Series,
    context: CandidateContext,
) -> OptionCandidate:
    """Build an ``OptionCandidate`` from a filtered option-row record."""
    volume = int(row["volume"])
    open_interest = int(row["openInterest"])
    strike = float(row["strike"])
    return OptionCandidate(
        ticker=ticker,
        strike=strike,
        expiration=context.expiration,
        contract_type="call",
        bid=float(row.get("bid", 0)),
        ask=float(row.get("_price", row["ask"])),
        last_price=float(row.get("lastPrice", 0)),
        volume=volume,
        open_interest=open_interest,
        implied_volatility=float(row.get("impliedVolatility", 0)),
        underlying_price=context.underlying_price,
        dte=context.dte,
        volume_oi_ratio=volume_oi_ratio(volume, open_interest),
        proximity_pct=proximity_pct(context.underlying_price, strike),
        contract_symbol=str(row.get("contractSymbol", "")),
        days_to_earnings=context.days_to_earnings,
    )
