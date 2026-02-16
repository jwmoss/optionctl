"""Polygon.io data source for option chain fetching."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime

import httpx

from optionctl.cache import write_chain_cache, write_no_options_cache

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DTE = 14
_RATE_LIMIT_DELAY = 12.0  # seconds between requests (free tier: 5 req/min)


def _get_api_key() -> str:
    """Read the Polygon API key from the environment.

    Returns:
        The API key string.

    Raises:
        RuntimeError: If the POLYGON_API_KEY env var is not set.
    """
    key = os.environ.get("POLYGON_API_KEY", "")
    if not key:
        msg = "POLYGON_API_KEY environment variable is required for --source polygon"
        raise RuntimeError(msg)
    return key


def _map_contract(raw: dict) -> dict:
    """Map a Polygon snapshot contract to yfinance-equivalent field names.

    Args:
        raw: Raw contract dict from Polygon API response.

    Returns:
        Dict with yfinance-compatible field names.
    """
    details = raw.get("details", {})
    day = raw.get("day", {})
    greeks = raw.get("greeks", {})

    contract_type = details.get("contract_type", "call").lower()
    strike = details.get("strike_price", 0.0)

    last_quote = raw.get("last_quote", {})
    bid = last_quote.get("bid", 0.0)
    ask = last_quote.get("ask", 0.0)

    return {
        "contractSymbol": details.get("ticker", ""),
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "lastPrice": day.get("close", 0.0),
        "volume": day.get("volume", 0),
        "openInterest": raw.get("open_interest", 0),
        "impliedVolatility": greeks.get("delta", 0.0)
        if not raw.get("implied_volatility")
        else raw.get("implied_volatility", 0.0),
        "inTheMoney": raw.get("details", {}).get("strike_price", 0.0) != 0.0
        and _is_itm(contract_type, strike, raw.get("underlying_asset", {}).get("price", 0.0)),
        "contractType": contract_type,
        "expirationDate": details.get("expiration_date", ""),
    }


def _is_itm(contract_type: str, strike: float, underlying_price: float) -> bool:
    """Determine if a contract is in the money.

    Args:
        contract_type: "call" or "put".
        strike: Strike price.
        underlying_price: Current underlying price.

    Returns:
        True if the contract is in the money.
    """
    if underlying_price <= 0:
        return False
    if contract_type == "call":
        return strike < underlying_price
    return strike > underlying_price


def _group_contracts(
    results: list[dict], today: date, max_dte: int
) -> tuple[dict[str, dict[str, list[dict]]], float]:
    """Group raw Polygon contracts by expiration and side.

    Args:
        results: Raw contract list from Polygon API.
        today: Current date for DTE filtering.
        max_dte: Maximum days to expiration (0 for all).

    Returns:
        Tuple of (chains dict, underlying_price).
    """
    from datetime import date as date_type

    chains: dict[str, dict[str, list[dict]]] = {}
    underlying_price = 0.0

    for raw in results:
        contract = _map_contract(raw)
        exp_str = contract.pop("expirationDate", "")
        contract_type = contract.pop("contractType", "call")

        if not exp_str:
            continue

        try:
            exp_date = date_type.fromisoformat(exp_str)
        except ValueError:
            continue

        dte = (exp_date - today).days
        if max_dte > 0 and dte > max_dte:
            continue

        asset = raw.get("underlying_asset", {})
        if asset.get("price", 0.0) > 0:
            underlying_price = asset["price"]

        if exp_str not in chains:
            chains[exp_str] = {"calls": [], "puts": []}

        side_key = "calls" if contract_type == "call" else "puts"
        chains[exp_str][side_key].append(contract)

    return chains, underlying_price


def _cache_polygon_chains(
    ticker: str,
    underlying_price: float,
    expirations: list[str],
    chains: dict[str, dict[str, list[dict]]],
) -> None:
    """Convert and cache Polygon chain data.

    Args:
        ticker: Stock ticker symbol.
        underlying_price: Current underlying price.
        expirations: Sorted list of expiration dates.
        chains: Chains dict with calls/puts lists.
    """
    import pandas as pd

    chains_df: dict[str, dict[str, pd.DataFrame]] = {}
    for exp, sides in chains.items():
        chains_df[exp] = {
            "calls": pd.DataFrame(sides["calls"]) if sides["calls"] else pd.DataFrame(),
            "puts": pd.DataFrame(sides["puts"]) if sides["puts"] else pd.DataFrame(),
        }

    write_chain_cache(ticker, underlying_price, expirations, chains_df)


class PolygonSource:
    """Option data source using Polygon.io snapshot API."""

    def __init__(self) -> None:
        """Initialize with API key from environment."""
        self._api_key = _get_api_key()
        self._last_request_time: float = 0.0

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.monotonic()

    def _fetch_snapshot(self, ticker: str) -> dict | None:
        """Fetch options snapshot from Polygon API.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Raw API response dict, or None on failure.
        """
        self._rate_limit()
        url = f"https://api.polygon.io/v3/snapshot/options/{ticker}"
        params = {"apiKey": self._api_key, "limit": 250}

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError:
            logger.warning("Polygon API error for %s", ticker)
            return None

    def fetch_ticker_data(
        self,
        ticker: str,
        *,
        fetch_enhanced: bool = True,  # noqa: ARG002
        max_dte: int = _DEFAULT_MAX_DTE,
    ) -> dict | None:
        """Fetch option chain data from Polygon.io.

        Args:
            ticker: Stock ticker symbol.
            fetch_enhanced: Ignored (Polygon doesn't provide earnings).
            max_dte: Maximum days to expiration to fetch (0 for all).

        Returns:
            Dict with chain data matching yfinance format, or None on failure.
        """
        data = self._fetch_snapshot(ticker)
        if data is None:
            return None

        results = data.get("results", [])
        if not results:
            write_no_options_cache(ticker)
            return None

        today = datetime.now(tz=UTC).date()
        chains, underlying_price = _group_contracts(results, today, max_dte)

        if not chains or underlying_price <= 0:
            return None

        expirations = sorted(chains.keys())
        _cache_polygon_chains(ticker, underlying_price, expirations, chains)

        return {
            "ticker": ticker,
            "underlying_price": underlying_price,
            "expirations": expirations,
            "chains": chains,
            "days_to_earnings": None,
        }
