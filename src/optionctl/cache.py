"""Disk-based caching for option chain data with market-aware TTL."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".config" / "optionctl" / "cache" / "chains"
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


def _is_cache_valid(cached_time: datetime) -> bool:
    """Check if cached data is still valid based on market hours.

    Args:
        cached_time: When the data was cached (UTC).

    Returns:
        True if cache is still valid.
    """
    if _is_market_open():
        # During market hours, 5 minute TTL
        return datetime.now(UTC) - cached_time <= timedelta(minutes=5)

    # After hours, valid until next market open
    # But only if cached after previous market close
    now_et = datetime.now(_ET)
    cached_et = cached_time.astimezone(_ET)

    # If cached today after 4pm, it's valid until tomorrow's open
    today_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if cached_et.date() == now_et.date() and cached_et >= today_close:
        return True

    # If it's a weekend and cached on Friday after close, still valid
    if now_et.weekday() >= 5:  # noqa: PLR2004
        # Find last Friday
        days_since_friday = (now_et.weekday() - 4) % 7
        last_friday = now_et - timedelta(days=days_since_friday)
        friday_close = last_friday.replace(hour=16, minute=0, second=0, microsecond=0)
        if cached_et >= friday_close:
            return True

    return False


def read_chain_cache(ticker: str) -> dict | None:
    """Read cached option chain data for a ticker.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Dict with chain data, or None if cache miss/stale.
    """
    path = _CACHE_DIR / f"{ticker.upper()}.json"

    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        cached_time = datetime.fromisoformat(data["timestamp"])

        if not _is_cache_valid(cached_time):
            logger.debug("Cache expired for %s", ticker)
            return None

        logger.debug("Cache hit for %s", ticker)
    except (json.JSONDecodeError, KeyError, TypeError, OSError, ValueError):
        return None
    else:
        return data


def write_chain_cache(
    ticker: str,
    underlying_price: float,
    expirations: list[str],
    chains: dict[str, pd.DataFrame],
    days_to_earnings: int | None = None,
) -> None:
    """Write option chain data to cache.

    Args:
        ticker: Stock ticker symbol.
        underlying_price: Current stock price.
        expirations: List of expiration date strings.
        chains: Dict mapping expiration to calls DataFrame.
        days_to_earnings: Days until next earnings, or None.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{ticker.upper()}.json"

        # Convert DataFrames to lists of dicts
        chains_data = {}
        for exp, df in chains.items():
            chains_data[exp] = df.to_dict(orient="records")

        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "ticker": ticker.upper(),
            "underlying_price": underlying_price,
            "expirations": expirations,
            "chains": chains_data,
            "days_to_earnings": days_to_earnings,
        }
        path.write_text(json.dumps(payload))
        logger.debug("Cached chain data for %s", ticker)
    except OSError:
        logger.debug("Failed to write cache for %s", ticker)


def clear_cache() -> int:
    """Clear all cached chain data.

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


def get_cache_stats() -> dict:
    """Get cache statistics.

    Returns:
        Dict with cache stats (count, size, tickers).
    """
    if not _CACHE_DIR.exists():
        return {"count": 0, "size_mb": 0.0, "tickers": []}

    files = list(_CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)
    tickers = [f.stem for f in files]

    return {
        "count": len(files),
        "size_mb": round(total_size / (1024 * 1024), 2),
        "tickers": sorted(tickers),
    }
