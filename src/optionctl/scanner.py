"""Core scanning engine for finding penny option candidates."""

from __future__ import annotations

import logging
import signal
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, TypeVar

import pandas as pd
import yfinance as yf

from optionctl.cache import read_chain_cache, write_chain_cache, write_no_options_cache
from optionctl.candidates import CandidateContext, build_candidate_from_row
from optionctl.filters import apply_filters
from optionctl.history import compute_vol_vs_avg, record_volume_snapshot
from optionctl.models import ScanResult, Side
from optionctl.scoring import score_candidates

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from optionctl.models import OptionCandidate, OptionDataSource, ScoringWeights

logger = logging.getLogger(__name__)

_interrupted = False

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds

_T = TypeVar("_T")


def _retry_with_backoff(
    operation: Callable[[], _T],
    *,
    warning_message: str,
    ticker: str,
) -> _T | None:
    """Run an operation with fixed retries and linear backoff."""
    for attempt in range(_MAX_RETRIES):
        try:
            return operation()
        except Exception:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY * (attempt + 1))
    logger.warning(warning_message, ticker)
    return None


def _fetch_with_retry(ticker: str) -> tuple[yf.Ticker, tuple[str, ...]] | None:
    """Fetch ticker and options with retry on failure.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Tuple of (Ticker, expirations) or None on failure.
    """

    def _fetch() -> tuple[yf.Ticker, tuple[str, ...]]:
        stock = yf.Ticker(ticker)
        return stock, stock.options

    return _retry_with_backoff(
        _fetch,
        warning_message="Failed to fetch options for %s",
        ticker=ticker,
    )


def _get_price_with_retry(stock: yf.Ticker, ticker: str) -> float | None:
    """Get underlying price with retry on failure.

    Args:
        stock: yfinance Ticker object.
        ticker: Ticker symbol for logging.

    Returns:
        Price or None on failure.
    """
    return _retry_with_backoff(
        lambda: float(stock.fast_info.last_price),
        warning_message="Failed to get price for %s",
        ticker=ticker,
    )


def _handle_sigint(signum: int, frame: object) -> None:  # noqa: ARG001
    """Set the interrupt flag so the scan loop exits between tickers."""
    global _interrupted  # noqa: PLW0603
    _interrupted = True


@contextmanager
def _interrupt_guard() -> Iterator[None]:
    """Install a SIGINT handler and restore the prior handler on exit."""
    global _interrupted  # noqa: PLW0603
    _interrupted = False
    prev_handler = signal.signal(signal.SIGINT, _handle_sigint)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, prev_handler)


def _process_tickers(
    tickers: list[str],
    progress_callback: Callable[[str, int, int], None] | None,
    interrupted_message: str,
    processor: Callable[[str], None],
) -> int:
    """Process tickers with shared progress and interrupt handling."""
    processed = 0
    with _interrupt_guard():
        for i, ticker in enumerate(tickers):
            if _interrupted:
                logger.info(interrupted_message, i, len(tickers))
                break

            if progress_callback:
                progress_callback(ticker, i + 1, len(tickers))

            processor(ticker)
            processed = i + 1
    return processed


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
) -> tuple[list[str], dict[str, dict[str, pd.DataFrame]]]:
    """Fetch option chains filtered by DTE.

    Args:
        stock: yfinance Ticker object.
        expirations: Available expiration dates.
        today: Current date.
        max_dte: Maximum DTE to fetch (0 for all).

    Returns:
        Tuple of (filtered_expirations, chains dict with calls+puts per exp).
    """
    chains: dict[str, dict[str, pd.DataFrame]] = {}
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
            chains[exp_str] = {"calls": chain.calls, "puts": chain.puts}
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

    # Convert to serializable format
    chains_data: dict[str, dict[str, list[dict]]] = {}
    for exp, side_dfs in chains.items():
        chains_data[exp] = {
            "calls": side_dfs["calls"].to_dict(orient="records"),
            "puts": side_dfs["puts"].to_dict(orient="records"),
        }

    return {
        "ticker": ticker,
        "underlying_price": underlying_price,
        "expirations": filtered_expirations,
        "chains": chains_data,
        "days_to_earnings": days_to_earnings,
    }


def _get_ticker_data(
    ticker: str,
    *,
    use_cache: bool,
    fetch_enhanced: bool,
    source: OptionDataSource | None = None,
) -> dict | None:
    """Get option chain data for a ticker from cache or fetch.

    Args:
        ticker: Stock ticker symbol.
        use_cache: Whether to use disk cache.
        fetch_enhanced: Whether to fetch enhanced signals.
        source: Optional data source; uses built-in yfinance fetcher if None.

    Returns:
        Dict with chain data, or None if unavailable/no options.
    """
    if use_cache:
        data = read_chain_cache(ticker)
        if data is not None:
            if data.get("no_options"):
                return None
            return data

    if source is not None:
        return source.fetch_ticker_data(ticker, fetch_enhanced=fetch_enhanced)

    return _fetch_and_cache_ticker(ticker, fetch_enhanced=fetch_enhanced)


def _sides_to_scan(side: Side) -> list[str]:
    """Return the list of side keys to iterate over.

    Args:
        side: Which option side(s) to scan.

    Returns:
        List of side keys ("calls", "puts", or both).
    """
    if side == Side.CALLS:
        return ["calls"]
    if side == Side.PUTS:
        return ["puts"]
    return ["calls", "puts"]


_SIDE_TO_CONTRACT_TYPE = {"calls": "call", "puts": "put"}


def scan_ticker(
    ticker: str,
    min_dte: int = 0,
    max_dte: int = 14,
    max_price: float = 0.01,
    min_volume: int = 100,
    *,
    side: Side = Side.CALLS,
    fetch_enhanced: bool = True,
    use_cache: bool = True,
    source: OptionDataSource | None = None,
) -> list[OptionCandidate]:
    """Scan a single ticker for penny OTM options.

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price (default $0.01).
        min_volume: Minimum contract volume.
        side: Which option side(s) to scan.
        fetch_enhanced: Whether to fetch enhanced signals (earnings, etc.).
        use_cache: Whether to use disk cache for results.
        source: Optional data source; uses built-in yfinance fetcher if None.

    Returns:
        List of qualifying option candidates.
    """
    data = _get_ticker_data(
        ticker, use_cache=use_cache, fetch_enhanced=fetch_enhanced, source=source
    )
    if data is None:
        return []

    today = datetime.now(tz=UTC).date()
    candidates: list[OptionCandidate] = []
    underlying_price = data["underlying_price"]
    days_to_earnings = data.get("days_to_earnings")
    scan_sides = _sides_to_scan(side)

    for exp_str, chain_data in data["chains"].items():
        exp_date = _parse_expiration(exp_str)
        dte = (exp_date - today).days

        if dte < min_dte or dte > max_dte:
            continue

        context = CandidateContext(
            expiration=exp_date,
            underlying_price=underlying_price,
            dte=dte,
            days_to_earnings=days_to_earnings,
        )

        for side_key in scan_sides:
            chain_records = chain_data.get(side_key, [])
            contract_type = _SIDE_TO_CONTRACT_TYPE[side_key]

            df = pd.DataFrame(chain_records)
            if df.empty:
                continue

            filtered = apply_filters(df, underlying_price, max_price, min_volume)
            candidates.extend(
                build_candidate_from_row(
                    ticker=ticker,
                    row=row,
                    context=context,
                    contract_type=contract_type,
                )
                for row in filtered.to_dict(orient="records")
            )

    for c in candidates:
        c.vol_vs_avg = compute_vol_vs_avg(c.volume, c.contract_symbol)

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
    side: Side = Side.CALLS,
    fetch_enhanced: bool = True,
    use_cache: bool = True,
    source: OptionDataSource | None = None,
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
        side: Which option side(s) to scan.
        fetch_enhanced: Whether to fetch enhanced signals.
        use_cache: Whether to use disk cache for results.
        source: Optional data source; uses built-in yfinance fetcher if None.

    Returns:
        ScanResult with scored candidates and scan metadata.
    """
    result = ScanResult()
    all_candidates: list[OptionCandidate] = []

    def _scan_one_ticker(ticker: str) -> None:
        candidates = scan_ticker(
            ticker,
            min_dte,
            max_dte,
            max_price,
            min_volume,
            side=side,
            fetch_enhanced=fetch_enhanced,
            use_cache=use_cache,
            source=source,
        )
        if candidates:
            result.tickers_with_options += 1
            all_candidates.extend(candidates)

    result.tickers_scanned = _process_tickers(
        tickers,
        progress_callback,
        "Scan interrupted after %d/%d tickers",
        _scan_one_ticker,
    )

    record_volume_snapshot(all_candidates)
    result.candidates = score_candidates(all_candidates, weights)
    return result


def warm_cache(
    tickers: list[str],
    progress_callback: Callable[[str, int, int], None] | None = None,
    max_dte: int = _DEFAULT_MAX_DTE,
    *,
    source: OptionDataSource | None = None,
) -> int:
    """Pre-fetch and cache option chain data for tickers.

    Args:
        tickers: List of ticker symbols to cache.
        progress_callback: Optional callback(ticker, current, total) for progress.
        max_dte: Maximum days to expiration to fetch (0 for all).
        source: Optional data source; uses built-in yfinance fetcher if None.

    Returns:
        Number of tickers successfully cached.
    """
    cached_count = 0

    def _warm_one_ticker(ticker: str) -> None:
        nonlocal cached_count
        if source is not None:
            data = source.fetch_ticker_data(ticker, max_dte=max_dte)
        else:
            data = _fetch_and_cache_ticker(ticker, max_dte=max_dte)
        if data is not None:
            cached_count += 1

    _process_tickers(
        tickers,
        progress_callback,
        "Cache warming interrupted after %d/%d tickers",
        _warm_one_ticker,
    )

    return cached_count
