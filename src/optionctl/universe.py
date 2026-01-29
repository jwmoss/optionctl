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

# Curated list of consistently high-volume optionable stocks.
HIGH_VOLUME_TICKERS: list[str] = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMD",
    "AMZN",
    "META",
    "GOOG",
    "NFLX",
    "PLTR",
    "SOFI",
    "NIO",
    "BAC",
    "F",
    "T",
    "INTC",
    "SNAP",
    "UBER",
    "COIN",
    "MARA",
    "RIOT",
    "SQ",
    "PYPL",
    "DIS",
    "BABA",
    "PFE",
    "AAL",
    "CCL",
    "RIVN",
    "LCID",
    "WBD",
    "HOOD",
    "PLUG",
    "MU",
    "QCOM",
    "JPM",
    "WFC",
    "C",
    "GS",
    "V",
    "MA",
    "CRM",
    "ORCL",
    "XOM",
    "CVX",
    "KO",
    "PEP",
    "WMT",
    "HD",
    "BA",
]


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


def get_top_volume_tickers(top_n: int = 50) -> list[str]:
    """Get the top N high-volume optionable tickers.

    Args:
        top_n: Number of tickers to return.

    Returns:
        List of ticker symbols.
    """
    return HIGH_VOLUME_TICKERS[:top_n]


def load_watchlist(path: str | Path) -> list[str]:
    """Load tickers from a watchlist file (one ticker per line).

    Args:
        path: Path to the watchlist file.

    Returns:
        List of ticker symbols.

    Raises:
        FileNotFoundError: If the watchlist file does not exist.
    """
    filepath = Path(path)
    if not filepath.exists():
        msg = f"Watchlist file not found: {filepath}"
        raise FileNotFoundError(msg)

    tickers: list[str] = []
    with filepath.open() as f:
        for line in f:
            ticker = line.strip().upper()
            if ticker and not ticker.startswith("#"):
                tickers.append(ticker)
    return tickers


def get_tickers(
    universe: str = "sp500",
    watchlist_file: str | None = None,
    top_n: int = 50,
    *,
    use_cache: bool = True,
) -> list[str]:
    """Get tickers based on the selected universe.

    Args:
        universe: One of "sp500", "volume", or "watchlist".
        watchlist_file: Path to watchlist file (required if universe is "watchlist").
        top_n: Number of tickers for the "volume" universe.
        use_cache: If ``False``, bypass the disk cache for remote sources.

    Returns:
        List of ticker symbols.

    Raises:
        ValueError: If universe is unknown or watchlist_file is missing.
    """
    if universe == "sp500":
        return get_sp500_tickers(use_cache=use_cache)
    if universe == "volume":
        return get_top_volume_tickers(top_n)
    if universe == "watchlist":
        if watchlist_file is None:
            msg = "--watchlist-file is required when using --universe watchlist"
            raise ValueError(msg)
        return load_watchlist(watchlist_file)
    msg = f"Unknown universe: {universe}"
    raise ValueError(msg)
