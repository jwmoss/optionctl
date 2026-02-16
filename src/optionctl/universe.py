"""Stock universe providers for optionctl."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from io import StringIO
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Disk-based ticker cache (JSON with TTL)
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".cache" / "optionctl"
_DEFAULT_TTL_SECONDS: int = 86_400  # 24 hours


def _read_ticker_cache(name: str, ttl: int = _DEFAULT_TTL_SECONDS) -> list[str] | None:
    """Read cached tickers from disk if the cache file is fresh.

    Args:
        name: Cache file stem (e.g., ``"sp500"``).
        ttl: Maximum age in seconds before the cache is considered stale.

    Returns:
        Cached ticker list, or ``None`` if missing, stale, or corrupt.
    """
    path = _CACHE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data["timestamp"] > ttl:
            logger.debug("Ticker cache expired for %s", name)
            return None
        tickers: list[str] = data["tickers"]
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return None
    logger.debug("Ticker cache hit for %s (%d tickers)", name, len(tickers))
    return tickers


def _write_ticker_cache(name: str, tickers: list[str]) -> None:
    """Write tickers to a disk cache file.

    Args:
        name: Cache file stem (e.g., ``"sp500"``).
        tickers: Ticker symbols to cache.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{name}.json"
        payload = {"timestamp": time.time(), "tickers": tickers}
        path.write_text(json.dumps(payload))
        logger.debug("Cached %d tickers as %s", len(tickers), name)
    except OSError:
        logger.debug("Failed to write ticker cache for %s", name)


# ---------------------------------------------------------------------------
# Wikipedia fetch
# ---------------------------------------------------------------------------


def _fetch_wikipedia_html(url: str) -> str:
    """Fetch HTML from Wikipedia with a browser-like User-Agent.

    Wikipedia blocks the default Python urllib User-Agent with HTTP 403.
    Using a standard browser User-Agent avoids this.

    Args:
        url: The Wikipedia URL to fetch.

    Returns:
        The HTML content as a string.
    """
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; optionctl/0.1; +https://github.com/jwmoss/optionctl)"
            ),
        },
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def get_sp500_tickers(*, use_cache: bool = True) -> list[str]:
    """Fetch S&P 500 component tickers from Wikipedia.

    Results are cached to disk for 24 hours to avoid repeated scraping.

    Args:
        use_cache: If ``False``, bypass the disk cache and fetch fresh data.

    Returns:
        List of ticker symbols for all S&P 500 components.
    """
    cache_key = "sp500"
    if use_cache:
        cached = _read_ticker_cache(cache_key)
        if cached is not None:
            return cached

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = _fetch_wikipedia_html(url)
    tables = pd.read_html(StringIO(html))
    df = tables[0]
    tickers: list[str] = df["Symbol"].tolist()
    # yfinance uses dashes instead of dots (e.g., BRK-B not BRK.B)
    tickers = [t.replace(".", "-") for t in tickers]
    _write_ticker_cache(cache_key, tickers)
    return tickers
