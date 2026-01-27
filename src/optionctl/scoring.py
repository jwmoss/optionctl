"""Composite scoring for option candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate

# Scoring weights
WEIGHT_VOLUME_OI = 40.0
WEIGHT_PROXIMITY = 35.0
WEIGHT_IV = 25.0

# Normalization caps
MAX_VOL_OI_RATIO = 5.0
MAX_PROXIMITY_PCT = 20.0
MAX_IV = 2.0


def score_volume_oi(vol_oi_ratio: float) -> float:
    """Score based on volume/OI ratio (0 to WEIGHT_VOLUME_OI).

    Higher ratios indicate more unusual activity relative to open interest.

    Args:
        vol_oi_ratio: Volume divided by open interest.

    Returns:
        Weighted score component.
    """
    normalized = min(vol_oi_ratio / MAX_VOL_OI_RATIO, 1.0)
    return normalized * WEIGHT_VOLUME_OI


def score_proximity(proximity_pct: float) -> float:
    """Score based on strike proximity to underlying (0 to WEIGHT_PROXIMITY).

    Closer strikes score higher since they have a better chance of going ITM.

    Args:
        proximity_pct: Distance from strike to underlying as a percentage.

    Returns:
        Weighted score component.
    """
    normalized = max(0.0, (MAX_PROXIMITY_PCT - proximity_pct) / MAX_PROXIMITY_PCT)
    return normalized * WEIGHT_PROXIMITY


def score_iv(implied_volatility: float) -> float:
    """Score based on implied volatility (0 to WEIGHT_IV).

    Higher IV suggests the market expects a larger move.

    Args:
        implied_volatility: Implied volatility as a decimal (e.g. 0.45 = 45%).

    Returns:
        Weighted score component.
    """
    normalized = min(implied_volatility / MAX_IV, 1.0)
    return normalized * WEIGHT_IV


def compute_score(
    vol_oi_ratio: float,
    proximity_pct: float,
    implied_volatility: float,
) -> float:
    """Compute composite score (0-100) for an option candidate.

    The score combines three signals:
    - Volume/OI ratio (40%): unusual activity
    - Proximity to strike (35%): likelihood of going ITM
    - Implied volatility (25%): expected move size

    Args:
        vol_oi_ratio: Volume divided by open interest.
        proximity_pct: Distance from strike to underlying as a percentage.
        implied_volatility: IV as a decimal.

    Returns:
        Composite score from 0 to 100.
    """
    return (
        score_volume_oi(vol_oi_ratio)
        + score_proximity(proximity_pct)
        + score_iv(implied_volatility)
    )


def score_candidates(candidates: list[OptionCandidate]) -> list[OptionCandidate]:
    """Score and sort a list of option candidates by composite score descending.

    Args:
        candidates: List of unscored candidates.

    Returns:
        Same list, scored and sorted highest first.
    """
    for c in candidates:
        c.score = compute_score(c.volume_oi_ratio, c.proximity_pct, c.implied_volatility)
    return sorted(candidates, key=lambda c: c.score, reverse=True)
