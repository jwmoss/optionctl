"""Disk-based caching for scan results with market-aware TTL."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".config" / "optionctl" / "cache" / "scans"
_ET = ZoneInfo("America/New_York")


def _get_next_market_open() -> datetime:
    """Get the next market open time (9:30 AM ET on a weekday).

    Returns:
        Next market open as a UTC datetime.
    """
    now_et = datetime.now(_ET)
    market_open_today = now_et.replace(hour=9, minute=30, second=0, microsecond=0)

    # If before market open today and it's a weekday, use today
    if now_et < market_open_today and now_et.weekday() < 5:  # noqa: PLR2004
        return market_open_today.astimezone(UTC)

    # Otherwise, find next weekday
    next_day = now_et + timedelta(days=1)
    while next_day.weekday() >= 5:  # noqa: PLR2004
        next_day += timedelta(days=1)

    return next_day.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(UTC)


def _is_market_open() -> bool:
    """Check if the US stock market is currently open.

    Returns:
        True if market is open (9:30 AM - 4:00 PM ET, weekdays).
    """
    now_et = datetime.now(_ET)

    # Weekend
    if now_et.weekday() >= 5:  # noqa: PLR2004
        return False

    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close


def _cache_key(ticker: str, min_dte: int, max_dte: int, max_price: float, min_volume: int) -> str:
    """Generate a cache key for scan parameters.

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price.
        min_volume: Minimum contract volume.

    Returns:
        Cache key string.
    """
    params = f"{ticker}:{min_dte}:{max_dte}:{max_price}:{min_volume}"
    return hashlib.sha256(params.encode()).hexdigest()[:16]


def read_scan_cache(
    ticker: str,
    min_dte: int,
    max_dte: int,
    max_price: float,
    min_volume: int,
) -> list[dict] | None:
    """Read cached scan results for a ticker.

    Cache is valid:
    - During market hours: 5 minutes
    - After market hours: until next market open

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price.
        min_volume: Minimum contract volume.

    Returns:
        List of candidate dicts, or None if cache miss/stale.
    """
    key = _cache_key(ticker, min_dte, max_dte, max_price, min_volume)
    path = _CACHE_DIR / f"{key}.json"

    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        cached_time = datetime.fromisoformat(data["timestamp"])

        # Determine TTL based on market hours
        if _is_market_open():
            # During market hours, 5 minute TTL
            if datetime.now(UTC) - cached_time > timedelta(minutes=5):
                logger.debug("Cache expired (market open) for %s", ticker)
                return None
        else:
            # After hours, valid until next market open
            next_open = _get_next_market_open()
            if cached_time < next_open - timedelta(days=1):
                # Cache is from before previous market close
                logger.debug("Cache expired (after hours) for %s", ticker)
                return None

        logger.debug("Cache hit for %s (%d candidates)", ticker, len(data["candidates"]))
        return data["candidates"]
    except (json.JSONDecodeError, KeyError, TypeError, OSError, ValueError):
        return None


def write_scan_cache(  # noqa: PLR0913
    ticker: str,
    min_dte: int,
    max_dte: int,
    max_price: float,
    min_volume: int,
    candidates: list[OptionCandidate],
) -> None:
    """Write scan results to cache.

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price.
        min_volume: Minimum contract volume.
        candidates: List of option candidates to cache.
    """
    key = _cache_key(ticker, min_dte, max_dte, max_price, min_volume)

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{key}.json"

        # Serialize candidates to dicts
        candidate_dicts = [
            {
                "ticker": c.ticker,
                "strike": c.strike,
                "expiration": c.expiration.isoformat(),
                "contract_type": c.contract_type,
                "bid": c.bid,
                "ask": c.ask,
                "last_price": c.last_price,
                "volume": c.volume,
                "open_interest": c.open_interest,
                "implied_volatility": c.implied_volatility,
                "underlying_price": c.underlying_price,
                "dte": c.dte,
                "volume_oi_ratio": c.volume_oi_ratio,
                "proximity_pct": c.proximity_pct,
                "contract_symbol": c.contract_symbol,
                "days_to_earnings": c.days_to_earnings,
            }
            for c in candidates
        ]

        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "ticker": ticker,
            "candidates": candidate_dicts,
        }
        path.write_text(json.dumps(payload))
        logger.debug("Cached %d candidates for %s", len(candidates), ticker)
    except OSError:
        logger.debug("Failed to write cache for %s", ticker)


def clear_scan_cache() -> int:
    """Clear all scan cache files.

    Returns:
        Number of cache files deleted.
    """
    if not _CACHE_DIR.exists():
        return 0

    count = 0
    for path in _CACHE_DIR.glob("*.json"):
        try:
            path.unlink()
            count += 1
        except OSError:
            pass
    return count
