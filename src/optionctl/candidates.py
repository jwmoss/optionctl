"""Utilities for constructing option candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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


def _to_float(value: object, *, default: float = 0.0) -> float:
    """Convert a loose row value to float, returning default on invalid input."""
    if not isinstance(value, int | float | str | bytes | bytearray):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: object, *, default: int = 0) -> int:
    """Convert a loose row value to int, returning default on invalid input."""
    if not isinstance(value, int | float | str | bytes | bytearray):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_candidate_from_row(
    *,
    ticker: str,
    row: Mapping[str, object],
    context: CandidateContext,
    contract_type: str = "call",
) -> OptionCandidate:
    """Build an ``OptionCandidate`` from a filtered option-row record."""
    volume = _to_int(row["volume"])
    open_interest = _to_int(row["openInterest"])
    strike = _to_float(row["strike"])
    if "volumeOiRatio" in row:
        vol_oi_ratio = _to_float(row["volumeOiRatio"])
    else:
        vol_oi_ratio = volume_oi_ratio(volume, open_interest)

    if "proximityPct" in row:
        proximity = _to_float(row["proximityPct"])
    else:
        proximity = proximity_pct(context.underlying_price, strike)

    ask_value = row["_price"] if "_price" in row else row["ask"]
    delta_value = row.get("delta")
    gamma_value = row.get("gamma")
    theta_value = row.get("theta")
    vega_value = row.get("vega")

    return OptionCandidate(
        ticker=ticker,
        strike=strike,
        expiration=context.expiration,
        contract_type=contract_type,
        bid=_to_float(row.get("bid", 0)),
        ask=_to_float(ask_value),
        last_price=_to_float(row.get("lastPrice", 0)),
        volume=volume,
        open_interest=open_interest,
        implied_volatility=_to_float(row.get("impliedVolatility", 0)),
        underlying_price=context.underlying_price,
        dte=context.dte,
        volume_oi_ratio=vol_oi_ratio,
        proximity_pct=proximity,
        contract_symbol=str(row.get("contractSymbol", "")),
        days_to_earnings=context.days_to_earnings,
        delta=None if delta_value is None else _to_float(delta_value),
        gamma=None if gamma_value is None else _to_float(gamma_value),
        theta=None if theta_value is None else _to_float(theta_value),
        vega=None if vega_value is None else _to_float(vega_value),
    )
