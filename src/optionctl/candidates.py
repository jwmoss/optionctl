"""Utilities for constructing option candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from optionctl.filters import proximity_pct, volume_oi_ratio
from optionctl.models import OptionCandidate

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date


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
    row: Mapping[str, object],
    context: CandidateContext,
) -> OptionCandidate:
    """Build an ``OptionCandidate`` from a filtered option-row record."""
    volume = int(cast("int | float | str", row["volume"]))
    open_interest = int(cast("int | float | str", row["openInterest"]))
    strike = float(cast("int | float | str", row["strike"]))
    if "volumeOiRatio" in row:
        vol_oi_ratio = float(cast("int | float | str", row["volumeOiRatio"]))
    else:
        vol_oi_ratio = volume_oi_ratio(volume, open_interest)

    if "proximityPct" in row:
        proximity = float(cast("int | float | str", row["proximityPct"]))
    else:
        proximity = proximity_pct(context.underlying_price, strike)

    ask_value = row["_price"] if "_price" in row else row["ask"]

    return OptionCandidate(
        ticker=ticker,
        strike=strike,
        expiration=context.expiration,
        bid=float(cast("int | float | str", row.get("bid", 0))),
        ask=float(cast("int | float | str", ask_value)),
        last_price=float(cast("int | float | str", row.get("lastPrice", 0))),
        volume=volume,
        open_interest=open_interest,
        implied_volatility=float(cast("int | float | str", row.get("impliedVolatility", 0))),
        underlying_price=context.underlying_price,
        dte=context.dte,
        volume_oi_ratio=vol_oi_ratio,
        proximity_pct=proximity,
        contract_symbol=str(row.get("contractSymbol", "")),
        days_to_earnings=context.days_to_earnings,
    )
