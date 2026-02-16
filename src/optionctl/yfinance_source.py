"""YFinance data source for option chain fetching."""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import yfinance as yf

if TYPE_CHECKING:
    import pandas as pd

from optionctl.cache import write_chain_cache, write_no_options_cache

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0
_DEFAULT_MAX_DTE = 15


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
        if isinstance(cal, dict) and "Earnings Date" in cal:
            earnings_list = cal["Earnings Date"]
            if earnings_list and len(earnings_list) > 0:
                next_earnings = earnings_list[0]
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


def _parse_expiration(exp_str: str) -> date:
    """Parse a yfinance expiration date string.

    Args:
        exp_str: Date string in YYYY-MM-DD format.

    Returns:
        Parsed date.
    """
    return date.fromisoformat(exp_str)


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


class YFinanceSource:
    """Option data source using yfinance."""

    def fetch_ticker_data(
        self, ticker: str, *, fetch_enhanced: bool = True, max_dte: int = _DEFAULT_MAX_DTE
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
            return None

        stock, expirations = result

        if not expirations:
            write_no_options_cache(ticker)
            return None

        today = datetime.now(tz=UTC).date()

        underlying_price = _get_price_with_retry(stock, ticker)
        if underlying_price is None:
            return None

        days_to_earnings: int | None = None
        if fetch_enhanced:
            days_to_earnings = _get_earnings_days(stock, today)

        filtered_expirations, chains = _fetch_chains_within_dte(stock, expirations, today, max_dte)

        if not chains:
            return None

        write_chain_cache(ticker, underlying_price, filtered_expirations, chains, days_to_earnings)

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
