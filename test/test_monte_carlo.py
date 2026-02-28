"""Tests for Monte Carlo p_itm simulation."""
from __future__ import annotations
import pytest
from optionctl.monte_carlo import simulate_p_itm


def test_atm_call_probability_near_half():
    """ATM call should have ~50% ITM probability."""
    p = simulate_p_itm(S0=100.0, K=100.0, sigma=0.3, T=30 / 365.0, N=100_000)
    assert 0.40 < p < 0.60, f"ATM p_itm={p:.3f} not near 0.5"


def test_deep_otm_near_zero():
    """Deep OTM call should have near-zero ITM probability."""
    p = simulate_p_itm(S0=100.0, K=200.0, sigma=0.3, T=5 / 365.0, N=50_000)
    assert p < 0.01, f"Deep OTM p_itm={p:.4f} should be near 0"


def test_deep_itm_near_one():
    """Deep ITM call should have near-one ITM probability."""
    p = simulate_p_itm(S0=200.0, K=100.0, sigma=0.3, T=30 / 365.0, N=50_000)
    assert p > 0.95, f"Deep ITM p_itm={p:.3f} should be near 1"


def test_zero_dte_returns_zero():
    """Zero DTE should return 0.0."""
    assert simulate_p_itm(100.0, 105.0, 0.3, 0.0) == 0.0


def test_zero_sigma_returns_zero():
    """Zero sigma should return 0.0."""
    assert simulate_p_itm(100.0, 105.0, 0.0, 30 / 365.0) == 0.0


def test_negative_dte_returns_zero():
    """Negative DTE should return 0.0."""
    assert simulate_p_itm(100.0, 105.0, 0.3, -1.0) == 0.0


def test_returns_float():
    """Result should be a float."""
    p = simulate_p_itm(100.0, 105.0, 0.3, 7 / 365.0)
    assert isinstance(p, float)
    assert 0.0 <= p <= 1.0
