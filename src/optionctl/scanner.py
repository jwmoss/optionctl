"""Core scanning engine for finding penny option candidates."""

from __future__ import annotations

import logging
import signal
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import yfinance as yf

from optionctl.filters import apply_filters, proximity_pct, volume_oi_ratio
from optionctl.models import OptionCandidate, ScanResult
from optionctl.scoring import score_candidates

if TYPE_CHECKING:
    from collections.abc import Callable

    from optionctl.models import ScoringWeights

logger = logging.getLogger(__name__)

_interrupted = False


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


def scan_ticker(  # noqa: C901
    ticker: str,
    min_dte: int = 0,
    max_dte: int = 14,
    max_price: float = 0.01,
    min_volume: int = 100,
    *,
    fetch_enhanced: bool = True,
) -> list[OptionCandidate]:
    """Scan a single ticker for penny OTM call options.

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price (default $0.01).
        min_volume: Minimum contract volume.
        fetch_enhanced: Whether to fetch enhanced signals (earnings, etc.).

    Returns:
        List of qualifying option candidates.
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
    except Exception:
        logger.warning("Failed to fetch options for %s", ticker)
        return []

    if not expirations:
        return []

    today = datetime.now(tz=UTC).date()
    candidates: list[OptionCandidate] = []

    # Get underlying price
    try:
        info = stock.fast_info
        underlying_price = float(info.last_price)
    except Exception:
        logger.warning("Failed to get price for %s", ticker)
        return []

    # Fetch enhanced data once per ticker
    days_to_earnings: int | None = None
    if fetch_enhanced:
        days_to_earnings = _get_earnings_days(stock, today)

    for exp_str in expirations:
        exp_date = _parse_expiration(exp_str)
        dte = (exp_date - today).days

        if dte < min_dte or dte > max_dte:
            continue

        try:
            chain = stock.option_chain(exp_str)
        except Exception:
            logger.warning("Failed to fetch chain for %s %s", ticker, exp_str)
            continue

        filtered = apply_filters(chain.calls, underlying_price, max_price, min_volume)

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
            )
            if candidates:
                result.tickers_with_options += 1
                all_candidates.extend(candidates)
    finally:
        signal.signal(signal.SIGINT, prev_handler)

    result.candidates = score_candidates(all_candidates, weights)
    return result
