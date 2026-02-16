"""Composite scoring for option candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from optionctl.models import (
    DEFAULT_WEIGHT_EARNINGS,
    DEFAULT_WEIGHT_IV,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_VOL_OI,
    DEFAULT_WEIGHT_VOLUME,
)

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, ScoringWeights

# Normalization caps
MAX_VOL_OI_RATIO = 5.0
MAX_VOLUME = 5000.0
MAX_PROXIMITY_PCT = 20.0
MAX_IV = 2.0
MAX_VOL_VS_AVG = 10.0

DEFAULT_WEIGHT_VOL_VS_AVG = 0.0


def score_volume_oi(vol_oi_ratio: float, weight: float = DEFAULT_WEIGHT_VOL_OI) -> float:
    """Score based on volume/OI ratio.

    Higher ratios indicate more unusual activity relative to open interest.

    Args:
        vol_oi_ratio: Volume divided by open interest.
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    normalized = min(vol_oi_ratio / MAX_VOL_OI_RATIO, 1.0)
    return normalized * weight


def score_volume(volume: int, weight: float = DEFAULT_WEIGHT_VOLUME) -> float:
    """Score based on raw contract volume.

    Higher volume means more liquidity and stronger conviction.

    Args:
        volume: Number of contracts traded today.
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    normalized = min(volume / MAX_VOLUME, 1.0)
    return normalized * weight


def score_proximity(proximity_pct: float, weight: float = DEFAULT_WEIGHT_PROXIMITY) -> float:
    """Score based on strike proximity to underlying.

    Closer strikes score higher since they have a better chance of going ITM.

    Args:
        proximity_pct: Distance from strike to underlying as a percentage.
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    normalized = max(0.0, (MAX_PROXIMITY_PCT - proximity_pct) / MAX_PROXIMITY_PCT)
    return normalized * weight


def score_iv(implied_volatility: float, weight: float = DEFAULT_WEIGHT_IV) -> float:
    """Score based on implied volatility.

    Higher IV suggests the market expects a larger move.

    Args:
        implied_volatility: Implied volatility as a decimal (e.g. 0.45 = 45%).
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    normalized = min(implied_volatility / MAX_IV, 1.0)
    return normalized * weight


def score_earnings(
    days_to_earnings: int | None, dte: int, weight: float = DEFAULT_WEIGHT_EARNINGS
) -> float:
    """Score based on earnings proximity.

    Full points if earnings falls before option expiration (catalyst play).
    No points if earnings is after expiration or unknown.

    Args:
        days_to_earnings: Days until next earnings, or None if unknown.
        dte: Days to expiration for the option.
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    if days_to_earnings is None or weight <= 0:
        return 0.0
    if 0 <= days_to_earnings <= dte:
        return weight  # earnings before expiry = full points
    return 0.0


def score_vol_vs_avg(vol_vs_avg: float | None, weight: float = DEFAULT_WEIGHT_VOL_VS_AVG) -> float:
    """Score based on current volume relative to historical average.

    Higher ratios indicate unusually active contracts compared to baseline.

    Args:
        vol_vs_avg: Volume-to-average multiplier, or None if unavailable.
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    if vol_vs_avg is None or weight <= 0:
        return 0.0
    normalized = min(vol_vs_avg / MAX_VOL_VS_AVG, 1.0)
    return normalized * weight


def compute_score(  # noqa: PLR0913
    vol_oi_ratio: float,
    volume: int,
    proximity_pct: float,
    implied_volatility: float,
    days_to_earnings: int | None = None,
    dte: int = 0,
    weights: ScoringWeights | None = None,
    vol_vs_avg: float | None = None,
) -> float:
    """Compute composite score for an option candidate.

    The score combines multiple signals:
    - Volume/OI ratio: unusual activity relative to open interest
    - Raw volume: liquidity and conviction
    - Proximity to strike: likelihood of going ITM
    - Implied volatility: expected move size
    - Earnings: catalyst before expiration
    - Vol vs avg: unusually high volume relative to baseline

    Args:
        vol_oi_ratio: Volume divided by open interest.
        volume: Raw contract volume.
        proximity_pct: Distance from strike to underlying as a percentage.
        implied_volatility: IV as a decimal.
        days_to_earnings: Days until earnings, or None.
        dte: Days to expiration.
        weights: Optional custom weights. Uses defaults if None.
        vol_vs_avg: Volume-to-average multiplier, or None.

    Returns:
        Composite score (0 to sum of weights).
    """
    if weights is None:
        w_vol_oi = DEFAULT_WEIGHT_VOL_OI
        w_volume = DEFAULT_WEIGHT_VOLUME
        w_proximity = DEFAULT_WEIGHT_PROXIMITY
        w_iv = DEFAULT_WEIGHT_IV
        w_earnings = DEFAULT_WEIGHT_EARNINGS
        w_vol_vs_avg = DEFAULT_WEIGHT_VOL_VS_AVG
    else:
        w_vol_oi = weights.vol_oi
        w_volume = weights.volume
        w_proximity = weights.proximity
        w_iv = weights.iv
        w_earnings = weights.earnings
        w_vol_vs_avg = weights.vol_vs_avg

    return (
        score_volume_oi(vol_oi_ratio, w_vol_oi)
        + score_volume(volume, w_volume)
        + score_proximity(proximity_pct, w_proximity)
        + score_iv(implied_volatility, w_iv)
        + score_earnings(days_to_earnings, dte, w_earnings)
        + score_vol_vs_avg(vol_vs_avg, w_vol_vs_avg)
    )


def score_candidates(
    candidates: list[OptionCandidate],
    weights: ScoringWeights | None = None,
) -> list[OptionCandidate]:
    """Score and sort a list of option candidates by composite score descending.

    Args:
        candidates: List of unscored candidates.
        weights: Optional custom weights. Uses defaults if None.

    Returns:
        Same list, scored and sorted highest first.
    """
    for c in candidates:
        c.score = compute_score(
            vol_oi_ratio=c.volume_oi_ratio,
            volume=c.volume,
            proximity_pct=c.proximity_pct,
            implied_volatility=c.implied_volatility,
            days_to_earnings=c.days_to_earnings,
            dte=c.dte,
            weights=weights,
            vol_vs_avg=c.vol_vs_avg,
        )
    return sorted(candidates, key=lambda c: c.score, reverse=True)
