"""Tests for the scoring module."""

from datetime import date

from optionctl.models import OptionCandidate, ScoringWeights
from optionctl.scoring import (
    DEFAULT_WEIGHT_IV,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_VOL_OI,
    DEFAULT_WEIGHT_VOLUME,
    compute_score,
    score_candidates,
    score_iv,
    score_proximity,
    score_volume,
    score_volume_oi,
)


def test_score_volume_oi_max() -> None:
    assert score_volume_oi(5.0) == DEFAULT_WEIGHT_VOL_OI
    assert score_volume_oi(10.0) == DEFAULT_WEIGHT_VOL_OI


def test_score_volume_oi_half() -> None:
    assert score_volume_oi(2.5) == DEFAULT_WEIGHT_VOL_OI / 2


def test_score_volume_oi_zero() -> None:
    assert score_volume_oi(0.0) == 0.0


def test_score_volume_oi_custom_weight() -> None:
    assert score_volume_oi(5.0, weight=50.0) == 50.0
    assert score_volume_oi(2.5, weight=50.0) == 25.0


def test_score_volume_max() -> None:
    assert score_volume(5000) == DEFAULT_WEIGHT_VOLUME
    assert score_volume(10000) == DEFAULT_WEIGHT_VOLUME


def test_score_volume_half() -> None:
    assert score_volume(2500) == DEFAULT_WEIGHT_VOLUME / 2


def test_score_volume_zero() -> None:
    assert score_volume(0) == 0.0


def test_score_volume_custom_weight() -> None:
    assert score_volume(5000, weight=20.0) == 20.0


def test_score_proximity_at_money() -> None:
    assert score_proximity(0.0) == DEFAULT_WEIGHT_PROXIMITY


def test_score_proximity_far_away() -> None:
    assert score_proximity(20.0) == 0.0
    assert score_proximity(30.0) == 0.0


def test_score_proximity_half() -> None:
    assert score_proximity(10.0) == DEFAULT_WEIGHT_PROXIMITY / 2


def test_score_iv_max() -> None:
    assert score_iv(2.0) == DEFAULT_WEIGHT_IV
    assert score_iv(3.0) == DEFAULT_WEIGHT_IV


def test_score_iv_half() -> None:
    assert score_iv(1.0) == DEFAULT_WEIGHT_IV / 2


def test_score_iv_zero() -> None:
    assert score_iv(0.0) == 0.0


def test_compute_score_perfect_defaults() -> None:
    score = compute_score(
        vol_oi_ratio=5.0,
        volume=5000,
        proximity_pct=0.0,
        implied_volatility=2.0,
    )
    assert score == 100.0


def test_compute_score_zero() -> None:
    score = compute_score(
        vol_oi_ratio=0.0,
        volume=0,
        proximity_pct=20.0,
        implied_volatility=0.0,
    )
    assert score == 0.0


def test_compute_score_custom_weights() -> None:
    weights = ScoringWeights(vol_oi=50.0, volume=0.0, proximity=50.0, iv=0.0)
    score = compute_score(
        vol_oi_ratio=5.0,
        volume=5000,
        proximity_pct=0.0,
        implied_volatility=2.0,
        weights=weights,
    )
    assert score == 100.0


def test_compute_score_volume_heavy() -> None:
    weights = ScoringWeights(vol_oi=0.0, volume=100.0, proximity=0.0, iv=0.0)
    # 2500 / 5000 = 0.5 * 100 = 50
    score = compute_score(
        vol_oi_ratio=5.0,
        volume=2500,
        proximity_pct=0.0,
        implied_volatility=2.0,
        weights=weights,
    )
    assert score == 50.0


def _make_candidate(
    vol_oi: float,
    prox: float,
    iv: float,
    volume: int = 500,
) -> OptionCandidate:
    return OptionCandidate(
        ticker="TEST",
        strike=100.0,
        expiration=date(2025, 1, 31),
        contract_type="call",
        bid=0.0,
        ask=0.01,
        last_price=0.01,
        volume=volume,
        open_interest=100,
        implied_volatility=iv,
        volume_oi_ratio=vol_oi,
        proximity_pct=prox,
    )


def test_score_candidates_sorts_descending() -> None:
    c1 = _make_candidate(1.0, 15.0, 0.5, volume=100)
    c2 = _make_candidate(5.0, 0.0, 2.0, volume=5000)
    c3 = _make_candidate(2.5, 10.0, 1.0, volume=2500)

    scored = score_candidates([c1, c2, c3])
    assert scored[0].score == 100.0  # c2 (perfect on all 4)
    assert scored[0] is c2
    assert scored[2] is c1  # c1 has worst metrics


def test_score_candidates_with_custom_weights() -> None:
    c1 = _make_candidate(0.0, 20.0, 0.0, volume=5000)  # only volume
    c2 = _make_candidate(5.0, 0.0, 2.0, volume=0)  # no volume

    weights = ScoringWeights(vol_oi=0.0, volume=100.0, proximity=0.0, iv=0.0)
    scored = score_candidates([c1, c2], weights)
    assert scored[0] is c1  # c1 wins because only volume matters
    assert scored[0].score == 100.0
    assert scored[1].score == 0.0


def test_score_candidates_empty() -> None:
    assert score_candidates([]) == []
