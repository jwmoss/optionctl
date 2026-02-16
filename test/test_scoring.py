"""Tests for the scoring module."""

import pytest

from optionctl.models import ScoringWeights
from optionctl.scoring import (
    DEFAULT_WEIGHT_EARNINGS,
    DEFAULT_WEIGHT_IV,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_VOL_OI,
    DEFAULT_WEIGHT_VOLUME,
    compute_score,
    score_candidates,
    score_earnings,
    score_iv,
    score_proximity,
    score_vol_vs_avg,
    score_volume,
    score_volume_oi,
)

# ---------------------------------------------------------------------------
# Individual score functions — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ratio", "weight", "expected"),
    [
        (5.0, DEFAULT_WEIGHT_VOL_OI, DEFAULT_WEIGHT_VOL_OI),
        (10.0, DEFAULT_WEIGHT_VOL_OI, DEFAULT_WEIGHT_VOL_OI),
        (2.5, DEFAULT_WEIGHT_VOL_OI, DEFAULT_WEIGHT_VOL_OI / 2),
        (0.0, DEFAULT_WEIGHT_VOL_OI, 0.0),
        (5.0, 50.0, 50.0),
        (2.5, 50.0, 25.0),
    ],
    ids=["max", "above-max", "half", "zero", "custom-max", "custom-half"],
)
def test_score_volume_oi(ratio, weight, expected):
    assert score_volume_oi(ratio, weight=weight) == expected


@pytest.mark.parametrize(
    ("volume", "weight", "expected"),
    [
        (5000, DEFAULT_WEIGHT_VOLUME, DEFAULT_WEIGHT_VOLUME),
        (10000, DEFAULT_WEIGHT_VOLUME, DEFAULT_WEIGHT_VOLUME),
        (2500, DEFAULT_WEIGHT_VOLUME, DEFAULT_WEIGHT_VOLUME / 2),
        (0, DEFAULT_WEIGHT_VOLUME, 0.0),
        (5000, 20.0, 20.0),
    ],
    ids=["max", "above-max", "half", "zero", "custom-weight"],
)
def test_score_volume(volume, weight, expected):
    assert score_volume(volume, weight=weight) == expected


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (0.0, DEFAULT_WEIGHT_PROXIMITY),
        (20.0, 0.0),
        (30.0, 0.0),
        (10.0, DEFAULT_WEIGHT_PROXIMITY / 2),
    ],
    ids=["at-money", "far-away", "very-far", "half"],
)
def test_score_proximity(pct, expected):
    assert score_proximity(pct) == expected


@pytest.mark.parametrize(
    ("iv", "expected"),
    [
        (2.0, DEFAULT_WEIGHT_IV),
        (3.0, DEFAULT_WEIGHT_IV),
        (1.0, DEFAULT_WEIGHT_IV / 2),
        (0.0, 0.0),
    ],
    ids=["max", "above-max", "half", "zero"],
)
def test_score_iv(iv, expected):
    assert score_iv(iv) == expected


@pytest.mark.parametrize(
    ("days_to_earn", "dte", "weight", "expected"),
    [
        (2, 5, DEFAULT_WEIGHT_EARNINGS, DEFAULT_WEIGHT_EARNINGS),  # earnings before expiry
        (5, 5, DEFAULT_WEIGHT_EARNINGS, DEFAULT_WEIGHT_EARNINGS),  # earnings on expiry day
        (0, 5, DEFAULT_WEIGHT_EARNINGS, DEFAULT_WEIGHT_EARNINGS),  # earnings today
        (10, 5, DEFAULT_WEIGHT_EARNINGS, 0.0),  # earnings after expiry
        (-1, 5, DEFAULT_WEIGHT_EARNINGS, 0.0),  # earnings already passed
        (None, 5, DEFAULT_WEIGHT_EARNINGS, 0.0),  # unknown earnings
        (2, 5, 0.0, 0.0),  # weight disabled
    ],
    ids=["before-expiry", "on-expiry", "today", "after-expiry", "passed", "unknown", "disabled"],
)
def test_score_earnings(days_to_earn, dte, weight, expected):
    assert score_earnings(days_to_earn, dte, weight=weight) == expected


# ---------------------------------------------------------------------------
# score_vol_vs_avg — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vol_vs_avg", "weight", "expected"),
    [
        (10.0, 20.0, 20.0),
        (20.0, 20.0, 20.0),
        (5.0, 20.0, 10.0),
        (0.0, 20.0, 0.0),
        (None, 20.0, 0.0),
        (5.0, 0.0, 0.0),
    ],
    ids=["max", "above-max", "half", "zero", "none", "weight-disabled"],
)
def test_score_vol_vs_avg(vol_vs_avg, weight, expected):
    assert score_vol_vs_avg(vol_vs_avg, weight=weight) == expected


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vol_oi", "volume", "prox", "iv", "earn", "dte", "weights", "expected"),
    [
        # Perfect score with earnings before expiry
        (5.0, 5000, 0.0, 2.0, 2, 5, None, 100.0),
        # Zero across the board
        (0.0, 0, 20.0, 0.0, None, 5, None, 0.0),
        # Without earnings signal
        (5.0, 5000, 0.0, 2.0, None, 5, None, 85.0),
        # Custom weights ignoring earnings
        (5.0, 5000, 0.0, 2.0, 2, 5, ScoringWeights(50.0, 0.0, 50.0, 0.0, 0.0), 100.0),
        # Volume-only scoring
        (5.0, 2500, 0.0, 2.0, None, 5, ScoringWeights(0.0, 100.0, 0.0, 0.0, 0.0), 50.0),
    ],
    ids=["perfect-all", "zero-all", "no-earnings", "custom-weights", "volume-heavy"],
)
def test_compute_score(vol_oi, volume, prox, iv, earn, dte, weights, expected):
    score = compute_score(
        vol_oi_ratio=vol_oi,
        volume=volume,
        proximity_pct=prox,
        implied_volatility=iv,
        days_to_earnings=earn,
        dte=dte,
        weights=weights,
    )
    assert score == expected


def test_compute_score_with_vol_vs_avg():
    weights = ScoringWeights(
        vol_oi=0.0, volume=0.0, proximity=0.0, iv=0.0, earnings=0.0, vol_vs_avg=100.0
    )
    score = compute_score(
        vol_oi_ratio=0.0,
        volume=0,
        proximity_pct=20.0,
        implied_volatility=0.0,
        vol_vs_avg=5.0,
        weights=weights,
    )
    assert score == 50.0


# ---------------------------------------------------------------------------
# score_candidates
# ---------------------------------------------------------------------------


def test_score_candidates_sorts_descending(make_candidate):
    c1 = make_candidate(volume_oi_ratio=1.0, proximity_pct=15.0, implied_volatility=0.5, volume=100)
    c2 = make_candidate(
        volume_oi_ratio=5.0,
        proximity_pct=0.0,
        implied_volatility=2.0,
        volume=5000,
        days_to_earnings=2,  # earnings before expiry (dte=3 default)
    )
    c3 = make_candidate(
        volume_oi_ratio=2.5, proximity_pct=10.0, implied_volatility=1.0, volume=2500
    )

    scored = score_candidates([c1, c2, c3])
    assert scored[0].score == 100.0
    assert scored[0] is c2
    assert scored[2] is c1


def test_score_candidates_with_custom_weights(make_candidate, volume_only_weights):
    c1 = make_candidate(
        volume_oi_ratio=0.0, proximity_pct=20.0, implied_volatility=0.0, volume=5000
    )
    c2 = make_candidate(volume_oi_ratio=5.0, proximity_pct=0.0, implied_volatility=2.0, volume=0)

    scored = score_candidates([c1, c2], volume_only_weights)
    assert scored[0] is c1
    assert scored[0].score == 100.0
    assert scored[1].score == 0.0


def test_score_candidates_empty():
    assert score_candidates([]) == []
