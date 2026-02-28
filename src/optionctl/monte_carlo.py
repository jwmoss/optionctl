"""Monte Carlo simulation for option probability estimation."""
from __future__ import annotations
import numpy as np


def simulate_p_itm(
    S0: float,
    K: float,
    sigma: float,
    T: float,
    *,
    N: int = 50_000,
) -> float:
    """Estimate probability of a call expiring in-the-money via GBM simulation.

    Uses Geometric Brownian Motion with zero drift (risk-neutral):
        S_T = S0 * exp(-0.5 * sigma^2 * T + sigma * sqrt(T) * Z)
    where Z ~ N(0, 1).

    Args:
        S0: Current underlying price.
        K: Strike price.
        sigma: Implied volatility as a decimal (e.g. 0.45 = 45%).
        T: Time to expiration in years (DTE / 365.0).
        N: Number of Monte Carlo paths (default 50,000).

    Returns:
        Estimated probability of S_T > K (0.0 to 1.0).
    """
    if T <= 0.0 or sigma <= 0.0 or S0 <= 0.0 or K <= 0.0:
        return 0.0

    Z = np.random.standard_normal(N)
    S_T = S0 * np.exp(-0.5 * sigma**2 * T + sigma * np.sqrt(T) * Z)
    return float((S_T > K).mean())
