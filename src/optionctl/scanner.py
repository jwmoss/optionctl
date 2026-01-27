"""Core scanning engine for finding penny option candidates."""

from __future__ import annotations

import logging
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


def _parse_expiration(exp_str: str) -> date:
    """Parse a yfinance expiration date string to a date object.

    Args:
        exp_str: Date string in YYYY-MM-DD format.

    Returns:
        Parsed date.
    """
    return date.fromisoformat(exp_str)


def scan_ticker(
    ticker: str,
    min_dte: int = 0,
    max_dte: int = 14,
    max_price: float = 0.01,
    min_volume: int = 100,
) -> list[OptionCandidate]:
    """Scan a single ticker for penny OTM call options.

    Args:
        ticker: Stock ticker symbol.
        min_dte: Minimum days to expiration.
        max_dte: Maximum days to expiration.
        max_price: Maximum ask price (default $0.01).
        min_volume: Minimum contract volume.

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
            candidate = OptionCandidate(
                ticker=ticker,
                strike=float(row["strike"]),
                expiration=exp_date,
                contract_type="call",
                bid=float(row.get("bid", 0)),
                ask=float(row["ask"]),
                last_price=float(row.get("lastPrice", 0)),
                volume=int(row["volume"]),
                open_interest=int(row["openInterest"]),
                implied_volatility=float(row.get("impliedVolatility", 0)),
                underlying_price=underlying_price,
                dte=dte,
                volume_oi_ratio=volume_oi_ratio(int(row["volume"]), int(row["openInterest"])),
                proximity_pct=proximity_pct(underlying_price, float(row["strike"])),
                contract_symbol=str(row.get("contractSymbol", "")),
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

    Returns:
        ScanResult with scored candidates and scan metadata.
    """
    result = ScanResult(tickers_scanned=len(tickers))
    all_candidates: list[OptionCandidate] = []

    for i, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(ticker, i + 1, len(tickers))

        candidates = scan_ticker(ticker, min_dte, max_dte, max_price, min_volume)
        if candidates:
            result.tickers_with_options += 1
            all_candidates.extend(candidates)

    result.candidates = score_candidates(all_candidates, weights)
    return result
