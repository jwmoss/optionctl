"""Composite scoring for option candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, ScoringWeights

# Normalization caps
MAX_VOL_OI_RATIO = 5.0
MAX_VOLUME = 5000.0
MAX_PROXIMITY_PCT = 20.0
MAX_IV = 2.0
MAX_DELTA = 0.20  # cap at 20 delta for penny options
MAX_VOLUME_VS_AVG = 5.0  # 5x average = max score

# Default weights (now sum to 100 with enhanced signals)
DEFAULT_WEIGHT_VOL_OI = 25.0
DEFAULT_WEIGHT_VOLUME = 10.0
DEFAULT_WEIGHT_PROXIMITY = 25.0
DEFAULT_WEIGHT_IV = 20.0
DEFAULT_WEIGHT_DELTA = 10.0
DEFAULT_WEIGHT_UNUSUAL_VOLUME = 10.0
DEFAULT_WEIGHT_EARNINGS = 0.0  # disabled by default


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


def score_delta(delta: float, weight: float = DEFAULT_WEIGHT_DELTA) -> float:
    """Score based on option delta (probability proxy).

    Higher delta = higher probability of finishing ITM.
    For penny options, we cap at 0.20 delta since these are OTM plays.

    Args:
        delta: Option delta (0.0 to 1.0 for calls).
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    if delta <= 0:
        return 0.0
    normalized = min(abs(delta) / MAX_DELTA, 1.0)
    return normalized * weight


def score_unusual_volume(
    volume_vs_avg: float, weight: float = DEFAULT_WEIGHT_UNUSUAL_VOLUME
) -> float:
    """Score based on volume relative to historical average.

    Higher multiples indicate unusual activity worth investigating.
    5x or more average volume = maximum score.

    Args:
        volume_vs_avg: Today's volume as multiple of average (e.g., 3.5 = 3.5x avg).
        weight: Maximum points for this component.

    Returns:
        Weighted score component.
    """
    if volume_vs_avg <= 0:
        return 0.0
    normalized = min(volume_vs_avg / MAX_VOLUME_VS_AVG, 1.0)
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
    if days_to_earnings <= dte:
        return weight  # earnings before expiry = full points
    return 0.0


def compute_score(  # noqa: PLR0913
    vol_oi_ratio: float,
    volume: int,
    proximity_pct: float,
    implied_volatility: float,
    delta: float = 0.0,
    volume_vs_avg: float = 0.0,
    days_to_earnings: int | None = None,
    dte: int = 0,
    weights: ScoringWeights | None = None,
) -> float:
    """Compute composite score for an option candidate.

    The score combines multiple signals:
    - Volume/OI ratio: unusual activity relative to open interest
    - Raw volume: liquidity and conviction
    - Proximity to strike: likelihood of going ITM
    - Implied volatility: expected move size
    - Delta: market-implied probability of profit
    - Unusual volume: activity vs historical average
    - Earnings: catalyst before expiration

    Args:
        vol_oi_ratio: Volume divided by open interest.
        volume: Raw contract volume.
        proximity_pct: Distance from strike to underlying as a percentage.
        implied_volatility: IV as a decimal.
        delta: Option delta.
        volume_vs_avg: Volume as multiple of average.
        days_to_earnings: Days until earnings, or None.
        dte: Days to expiration.
        weights: Optional custom weights. Uses defaults if None.

    Returns:
        Composite score (0 to sum of weights).
    """
    if weights is None:
        w_vol_oi = DEFAULT_WEIGHT_VOL_OI
        w_volume = DEFAULT_WEIGHT_VOLUME
        w_proximity = DEFAULT_WEIGHT_PROXIMITY
        w_iv = DEFAULT_WEIGHT_IV
        w_delta = DEFAULT_WEIGHT_DELTA
        w_unusual = DEFAULT_WEIGHT_UNUSUAL_VOLUME
        w_earnings = DEFAULT_WEIGHT_EARNINGS
    else:
        w_vol_oi = weights.vol_oi
        w_volume = weights.volume
        w_proximity = weights.proximity
        w_iv = weights.iv
        w_delta = weights.delta
        w_unusual = weights.unusual_volume
        w_earnings = weights.earnings

    return (
        score_volume_oi(vol_oi_ratio, w_vol_oi)
        + score_volume(volume, w_volume)
        + score_proximity(proximity_pct, w_proximity)
        + score_iv(implied_volatility, w_iv)
        + score_delta(delta, w_delta)
        + score_unusual_volume(volume_vs_avg, w_unusual)
        + score_earnings(days_to_earnings, dte, w_earnings)
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
            delta=c.delta,
            volume_vs_avg=c.volume_vs_avg,
            days_to_earnings=c.days_to_earnings,
            dte=c.dte,
            weights=weights,
        )
    return sorted(candidates, key=lambda c: c.score, reverse=True)
