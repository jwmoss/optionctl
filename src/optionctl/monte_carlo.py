"""Monte Carlo simulation for option probability estimation."""

from __future__ import annotations

import numpy as np


def simulate_p_itm(
    s0: float,
    k: float,
    sigma: float,
    t: float,
    *,
    n: int = 50_000,
) -> float:
    """Estimate probability of a call expiring in-the-money via GBM simulation.

    Uses Geometric Brownian Motion with zero drift (risk-neutral):
        S_T = S0 * exp(-0.5 * sigma^2 * T + sigma * sqrt(T) * Z)
    where Z ~ N(0, 1).

    Variance reduction via antithetic variates: each random draw Z is paired
    with -Z, giving ~50% variance reduction at no additional compute cost.

    Args:
        s0: Current underlying price.
        k: Strike price.
        sigma: Implied volatility as a decimal (e.g. 0.45 = 45%).
        t: Time to expiration in years (DTE / 365.0).
        n: Number of Monte Carlo paths (default 50,000).

    Returns:
        Estimated probability of S_T > K (0.0 to 1.0).
    """
    if t <= 0.0 or sigma <= 0.0 or s0 <= 0.0 or k <= 0.0:
        return 0.0

    rng = np.random.default_rng()
    # Antithetic variates: pair each Z with -Z for ~50% variance reduction at no cost.
    half = n // 2
    z = rng.standard_normal(half)
    z = np.concatenate([z, -z])
    s_t = s0 * np.exp(-0.5 * sigma**2 * t + sigma * np.sqrt(t) * z)
    return float((s_t > k).mean())
