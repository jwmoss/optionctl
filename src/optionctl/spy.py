"""SPY 0DTE options scanning."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import yfinance as yf

from optionctl.filters import apply_filters, proximity_pct, volume_oi_ratio
from optionctl.models import OptionCandidate, ScoringWeights
from optionctl.scoring import score_candidates

logger = logging.getLogger(__name__)

SPY_TICKER = "SPY"


def _get_spy_0dte_expiration() -> str | None:
    """Find today's expiration date in SPY's options chain.

    SPY has expirations on Monday, Wednesday, and Friday.

    Returns:
        Today's expiration string if available, None otherwise.
    """
    try:
        spy = yf.Ticker(SPY_TICKER)
        expirations = spy.options
    except Exception:
        logger.warning("Failed to fetch SPY options expirations")
        return None

    today_str = datetime.now(tz=UTC).date().isoformat()
    if today_str in expirations:
        return today_str
    return None


def _get_spy_price() -> float:
    """Get the current SPY price.

    Returns:
        Current SPY price.

    Raises:
        RuntimeError: If price cannot be fetched.
    """
    try:
        spy = yf.Ticker(SPY_TICKER)
        return float(spy.fast_info.last_price)
    except Exception as e:
        msg = f"Failed to get SPY price: {e}"
        raise RuntimeError(msg) from e


def find_penny_0dte(
    max_price: float = 0.01,
    min_volume: int = 100,
    weights: ScoringWeights | None = None,
) -> list[OptionCandidate]:
    """Find SPY 0DTE OTM call options priced at pennies.

    Args:
        max_price: Maximum ask price (default $0.01).
        min_volume: Minimum contract volume.
        weights: Optional custom scoring weights.

    Returns:
        Scored list of penny 0DTE candidates.
    """
    exp_str = _get_spy_0dte_expiration()
    if exp_str is None:
        logger.info("No SPY 0DTE expiration available today")
        return []

    spy_price = _get_spy_price()
    spy = yf.Ticker(SPY_TICKER)

    try:
        chain = spy.option_chain(exp_str)
    except Exception:
        logger.warning("Failed to fetch SPY option chain for %s", exp_str)
        return []

    filtered = apply_filters(chain.calls, spy_price, max_price, min_volume)
    exp_date = date.fromisoformat(exp_str)

    candidates: list[OptionCandidate] = []
    for _, row in filtered.iterrows():
        candidate = OptionCandidate(
            ticker=SPY_TICKER,
            strike=float(row["strike"]),
            expiration=exp_date,
            contract_type="call",
            bid=float(row.get("bid", 0)),
            ask=float(row["ask"]),
            last_price=float(row.get("lastPrice", 0)),
            volume=int(row["volume"]),
            open_interest=int(row["openInterest"]),
            implied_volatility=float(row.get("impliedVolatility", 0)),
            underlying_price=spy_price,
            dte=0,
            volume_oi_ratio=volume_oi_ratio(int(row["volume"]), int(row["openInterest"])),
            proximity_pct=proximity_pct(spy_price, float(row["strike"])),
            contract_symbol=str(row.get("contractSymbol", "")),
        )
        candidates.append(candidate)

    return score_candidates(candidates, weights)


def find_momentum_0dte(
    max_distance_pct: float = 2.0,
    min_volume: int = 500,
    weights: ScoringWeights | None = None,
) -> list[OptionCandidate]:
    """Find SPY 0DTE near-the-money calls for momentum/gamma scalping.

    Targets contracts close to the current price where gamma is highest,
    offering the largest delta change per dollar move in SPY.

    Args:
        max_distance_pct: Maximum distance from underlying as a percentage.
        min_volume: Minimum contract volume.
        weights: Optional custom scoring weights.

    Returns:
        Scored list of momentum candidates sorted by proximity.
    """
    exp_str = _get_spy_0dte_expiration()
    if exp_str is None:
        logger.info("No SPY 0DTE expiration available today")
        return []

    spy_price = _get_spy_price()
    spy = yf.Ticker(SPY_TICKER)

    try:
        chain = spy.option_chain(exp_str)
    except Exception:
        logger.warning("Failed to fetch SPY option chain for %s", exp_str)
        return []

    calls_df = chain.calls.copy()
    calls_df = calls_df.dropna(subset=["ask", "volume", "openInterest"])
    calls_df = calls_df[calls_df["volume"] >= min_volume]

    # Filter to near-the-money contracts
    calls_df = calls_df.copy()
    calls_df["proximityPct"] = calls_df["strike"].apply(
        lambda s: proximity_pct(spy_price, s),
    )
    calls_df = calls_df[calls_df["proximityPct"] <= max_distance_pct]

    # Only OTM calls (strike above current price)
    calls_df = calls_df[calls_df["strike"] > spy_price]

    exp_date = date.fromisoformat(exp_str)

    candidates: list[OptionCandidate] = []
    for _, row in calls_df.iterrows():
        candidate = OptionCandidate(
            ticker=SPY_TICKER,
            strike=float(row["strike"]),
            expiration=exp_date,
            contract_type="call",
            bid=float(row.get("bid", 0)),
            ask=float(row["ask"]),
            last_price=float(row.get("lastPrice", 0)),
            volume=int(row["volume"]),
            open_interest=int(row["openInterest"]),
            implied_volatility=float(row.get("impliedVolatility", 0)),
            underlying_price=spy_price,
            dte=0,
            volume_oi_ratio=volume_oi_ratio(int(row["volume"]), int(row["openInterest"])),
            proximity_pct=float(row["proximityPct"]),
            contract_symbol=str(row.get("contractSymbol", "")),
        )
        candidates.append(candidate)

    return score_candidates(candidates, weights)
