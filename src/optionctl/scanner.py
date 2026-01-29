"""Core scanning engine for finding penny option candidates."""

from __future__ import annotations

import logging
import signal
import time
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pandas as pd
import yfinance as yf

from optionctl.cache import read_chain_cache, write_chain_cache, write_no_options_cache
from optionctl.filters import apply_filters, proximity_pct, volume_oi_ratio
from optionctl.models import OptionCandidate, ScanResult
from optionctl.scoring import score_candidates

if TYPE_CHECKING:
    from collections.abc import Callable

    from optionctl.models import ScoringWeights

logger = logging.getLogger(__name__)

_interrupted = False

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds


def _fetch_with_retry(ticker: str) -> tuple[yf.Ticker, tuple[str, ...]] | None:
    """Fetch ticker and options with retry on failure.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Tuple of (Ticker, expirations) or None on failure.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            stock = yf.Ticker(ticker)
            expirations = stock.options
        except Exception:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))
        else:
            return stock, expirations
    logger.warning("Failed to fetch options for %s", ticker)
    return None


def _get_price_with_retry(stock: yf.Ticker, ticker: str) -> float | None:
    """Get underlying price with retry on failure.

    Args:
        stock: yfinance Ticker object.
        ticker: Ticker symbol for logging.

    Returns:
        Price or None on failure.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            price = float(stock.fast_info.last_price)
        except Exception:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))
        else:
            return price
    logger.warning("Failed to get price for %s", ticker)
    return None


def _handle_sigint(signum: int, frame: object) -> None:  # noqa: ARG001
    """Set the interrupt flag so the scan loop exits between tickers."""
    global _interrupted  # noqa: PLW0603
    _interrupted = True


def _parse_expiration(exp_str: str) -> date:
    """Parse a yfinance expiration date string to a date object.

    Args:
        exp_str: Date string in YYYY-MM-DD format.

    Returns:
        Parsed date.
    """
    return date.fromisoformat(exp_str)


def _get_earnings_days(stock: yf.Ticker, today: date) -> int | None:
    """Get days until next earnings date.

    Args:
        stock: yfinance Ticker object.
        today: Current date.

    Returns:
        Days until earnings, or None if unavailable.
    """
    try:
        cal = stock.calendar
        if cal is None:
            return None
        # calendar is a dict with 'Earnings Date' key containing a list
        if isinstance(cal, dict) and "Earnings Date" in cal:
            earnings_list = cal["Earnings Date"]
            if earnings_list and len(earnings_list) > 0:
                next_earnings = earnings_list[0]
                # Could be datetime.date or datetime.datetime
                if isinstance(next_earnings, date):
                    earnings_date = next_earnings
                elif hasattr(next_earnings, "date"):
                    earnings_date = next_earnings.date()
                else:
                    earnings_date = next_earnings
                return (earnings_date - today).days
    except Exception:  # noqa: S110
        pass
    return None


_DEFAULT_MAX_DTE = 14


def _fetch_chains_within_dte(
    stock: yf.Ticker,
    expirations: tuple[str, ...],
    today: date,
    max_dte: int,
) -> tuple[list[str], dict[str, pd.DataFrame]]:
    """Fetch option chains filtered by DTE.

    Args:
        stock: yfinance Ticker object.
        expirations: Available expiration dates.
        today: Current date.
        max_dte: Maximum DTE to fetch (0 for all).

    Returns:
        Tuple of (filtered_expirations, chains dict).
    """
    chains: dict[str, pd.DataFrame] = {}
    filtered_expirations: list[str] = []

    for exp_str in expirations:
        exp_date = _parse_expiration(exp_str)
        dte = (exp_date - today).days

        # Skip if beyond max_dte (unless max_dte is 0 meaning fetch all)
        if max_dte > 0 and dte > max_dte:
            continue

        filtered_expirations.append(exp_str)
        try:
            chain = stock.option_chain(exp_str)
            chains[exp_str] = chain.calls
        except Exception:
            logger.warning("Failed to fetch chain for %s %s", stock.ticker, exp_str)
            continue

    return filtered_expirations, chains


def _fetch_and_cache_ticker(
    ticker: str, *, fetch_enhanced: bool = True, max_dte: int = _DEFAULT_MAX_DTE
) -> dict | None:
    """Fetch option chain data for a ticker and cache it.

    Args:
        ticker: Stock ticker symbol.
        fetch_enhanced: Whether to fetch earnings data.
        max_dte: Maximum days to expiration to fetch (0 for all).

    Returns:
        Dict with chain data, or None on failure.
    """
    result = _fetch_with_retry(ticker)
    if result is None:
        return None  # API error - don't cache, might work later

    stock, expirations = result

    # No options available (not an error, just skip silently)
    if not expirations:
        write_no_options_cache(ticker)
        return None

    today = datetime.now(tz=UTC).date()

    underlying_price = _get_price_with_retry(stock, ticker)
    if underlying_price is None:
        return None

    # Fetch earnings
    days_to_earnings: int | None = None
    if fetch_enhanced:
        days_to_earnings = _get_earnings_days(stock, today)

    # Fetch chains (filtered by max_dte if specified)
    filtered_expirations, chains = _fetch_chains_within_dte(stock, expirations, today, max_dte)

    if not chains:
        return None

    # Cache it
    write_chain_cache(ticker, underlying_price, filtered_expirations, chains, days_to_earnings)

    return {
        "ticker": ticker,
        "underlying_price": underlying_price,
        "expirations": filtered_expirations,
        "chains": {exp: df.to_dict(orient="records") for exp, df in chains.items()},
        "days_to_earnings": days_to_earnings,
    }


def _get_ticker_data(ticker: str, *, use_cache: bool, fetch_enhanced: bool) -> dict | None:
    """Get option chain data for a ticker from cache or fetch.

    Args:
        ticker: Stock ticker symbol.
        use_cache: Whether to use disk cache.
        fetch_enhanced: Whether to fetch enhanced signals.

    Returns:
        Dict with chain data, or None if unavailable/no options.
    """
    if use_cache:
        data = read_chain_cache(ticker)
        if data is not None:
            # Return None for no-options markers to signal skip
            if data.get("no_options"):
                return None
            return data

    return _fetch_and_cache_ticker(ticker, fetch_enhanced=fetch_enhanced)


def scan_ticker(
    ticker: str,
    min_dte: int = 0,
    max_dte: int = 14,
    max_price: float = 0.01,
    min_volume: int = 100,
    *,
    fetch_enhanced: bool = True,
    use_cache: bool = True,
) -> list[OptionCandidate]:
    """Scan a single ticker for penny OTM call options.

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price (default $0.01).
        min_volume: Minimum contract volume.
        fetch_enhanced: Whether to fetch enhanced signals (earnings, etc.).
        use_cache: Whether to use disk cache for results.

    Returns:
        List of qualifying option candidates.
    """
    data = _get_ticker_data(ticker, use_cache=use_cache, fetch_enhanced=fetch_enhanced)
    if data is None:
        return []

    today = datetime.now(tz=UTC).date()
    candidates: list[OptionCandidate] = []
    underlying_price = data["underlying_price"]
    days_to_earnings = data.get("days_to_earnings")

    for exp_str, chain_records in data["chains"].items():
        exp_date = _parse_expiration(exp_str)
        dte = (exp_date - today).days

        if dte < min_dte or dte > max_dte:
            continue

        # Convert cached records back to DataFrame
        df = pd.DataFrame(chain_records)
        if df.empty:
            continue

        filtered = apply_filters(df, underlying_price, max_price, min_volume)

        for _, row in filtered.iterrows():
            volume = int(row["volume"])

            candidate = OptionCandidate(
                ticker=ticker,
                strike=float(row["strike"]),
                expiration=exp_date,
                contract_type="call",
                bid=float(row.get("bid", 0)),
                ask=float(row.get("_price", row["ask"])),
                last_price=float(row.get("lastPrice", 0)),
                volume=volume,
                open_interest=int(row["openInterest"]),
                implied_volatility=float(row.get("impliedVolatility", 0)),
                underlying_price=underlying_price,
                dte=dte,
                volume_oi_ratio=volume_oi_ratio(volume, int(row["openInterest"])),
                proximity_pct=proximity_pct(underlying_price, float(row["strike"])),
                contract_symbol=str(row.get("contractSymbol", "")),
                days_to_earnings=days_to_earnings,
            )
            candidates.append(candidate)

    return candidates


def scan_universe(
    tickers: list[str],
    min_dte: int = 0,
    max_dte: int = 14,
    max_price: float = 0.01,
    min_volume: int = 100,
    progress_callback: Callable[[str, int, int], None] | None = None,
    weights: ScoringWeights | None = None,
    *,
    fetch_enhanced: bool = True,
    use_cache: bool = True,
) -> ScanResult:
    """Scan multiple tickers for penny option candidates.

    Args:
        tickers: List of ticker symbols to scan.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price.
        min_volume: Minimum contract volume.
        progress_callback: Optional callback(ticker, current, total) for progress.
        weights: Optional custom scoring weights.
        fetch_enhanced: Whether to fetch enhanced signals.
        use_cache: Whether to use disk cache for results.

    Returns:
        ScanResult with scored candidates and scan metadata.
    """
    global _interrupted  # noqa: PLW0603
    _interrupted = False
    prev_handler = signal.signal(signal.SIGINT, _handle_sigint)

    result = ScanResult(tickers_scanned=len(tickers))
    all_candidates: list[OptionCandidate] = []

    try:
        for i, ticker in enumerate(tickers):
            if _interrupted:
                logger.info("Scan interrupted after %d/%d tickers", i, len(tickers))
                result.tickers_scanned = i
                break

            if progress_callback:
                progress_callback(ticker, i + 1, len(tickers))

            candidates = scan_ticker(
                ticker,
                min_dte,
                max_dte,
                max_price,
                min_volume,
                fetch_enhanced=fetch_enhanced,
                use_cache=use_cache,
            )
            if candidates:
                result.tickers_with_options += 1
                all_candidates.extend(candidates)
    finally:
        signal.signal(signal.SIGINT, prev_handler)

    result.candidates = score_candidates(all_candidates, weights)
    return result


def warm_cache(
    tickers: list[str],
    progress_callback: Callable[[str, int, int], None] | None = None,
    max_dte: int = _DEFAULT_MAX_DTE,
) -> int:
    """Pre-fetch and cache option chain data for tickers.

    Args:
        tickers: List of ticker symbols to cache.
        progress_callback: Optional callback(ticker, current, total) for progress.
        max_dte: Maximum days to expiration to fetch (0 for all).

    Returns:
        Number of tickers successfully cached.
    """
    global _interrupted  # noqa: PLW0603
    _interrupted = False
    prev_handler = signal.signal(signal.SIGINT, _handle_sigint)

    cached_count = 0

    try:
        for i, ticker in enumerate(tickers):
            if _interrupted:
                logger.info("Cache warming interrupted after %d/%d tickers", i, len(tickers))
                break

            if progress_callback:
                progress_callback(ticker, i + 1, len(tickers))

            if _fetch_and_cache_ticker(ticker, max_dte=max_dte) is not None:
                cached_count += 1
    finally:
        signal.signal(signal.SIGINT, prev_handler)

    return cached_count
