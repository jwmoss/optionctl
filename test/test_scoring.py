"""Tests for the scoring module."""

from datetime import date

from optionctl.models import OptionCandidate
from optionctl.scoring import (
    compute_score,
    score_candidates,
    score_iv,
    score_proximity,
    score_volume_oi,
)


def test_score_volume_oi_max() -> None:
    # Ratio of 5.0 or higher should give full weight (40)
    assert score_volume_oi(5.0) == 40.0
    assert score_volume_oi(10.0) == 40.0


def test_score_volume_oi_half() -> None:
    assert score_volume_oi(2.5) == 20.0


def test_score_volume_oi_zero() -> None:
    assert score_volume_oi(0.0) == 0.0


def test_score_proximity_at_money() -> None:
    # 0% distance = full score (35)
    assert score_proximity(0.0) == 35.0


def test_score_proximity_far_away() -> None:
    # 20% or more distance = 0
    assert score_proximity(20.0) == 0.0
    assert score_proximity(30.0) == 0.0


def test_score_proximity_half() -> None:
    # 10% distance = half score
    assert score_proximity(10.0) == 17.5


def test_score_iv_max() -> None:
    # IV of 200% or higher should give full weight (25)
    assert score_iv(2.0) == 25.0
    assert score_iv(3.0) == 25.0


def test_score_iv_half() -> None:
    assert score_iv(1.0) == 12.5


def test_score_iv_zero() -> None:
    assert score_iv(0.0) == 0.0


def test_compute_score_perfect() -> None:
    # Perfect score: high vol/OI, at-money, high IV
    score = compute_score(vol_oi_ratio=5.0, proximity_pct=0.0, implied_volatility=2.0)
    assert score == 100.0


def test_compute_score_zero() -> None:
    score = compute_score(vol_oi_ratio=0.0, proximity_pct=20.0, implied_volatility=0.0)
    assert score == 0.0


def test_compute_score_mixed() -> None:
    score = compute_score(vol_oi_ratio=2.5, proximity_pct=10.0, implied_volatility=1.0)
    # 20.0 + 17.5 + 12.5 = 50.0
    assert score == 50.0


def _make_candidate(vol_oi: float, prox: float, iv: float) -> OptionCandidate:
    return OptionCandidate(
        ticker="TEST",
        strike=100.0,
        expiration=date(2025, 1, 31),
        contract_type="call",
        bid=0.0,
        ask=0.01,
        last_price=0.01,
        volume=500,
        open_interest=100,
        implied_volatility=iv,
        volume_oi_ratio=vol_oi,
        proximity_pct=prox,
    )


def test_score_candidates_sorts_descending() -> None:
    c1 = _make_candidate(1.0, 15.0, 0.5)
    c2 = _make_candidate(5.0, 0.0, 2.0)
    c3 = _make_candidate(2.5, 10.0, 1.0)

    scored = score_candidates([c1, c2, c3])
    assert scored[0].score == 100.0  # c2
    assert scored[1].score == 50.0  # c3
    assert scored[0] is c2
    assert scored[1] is c3
    assert scored[2] is c1


def test_score_candidates_empty() -> None:
    assert score_candidates([]) == []
