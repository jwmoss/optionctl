"""Zero-DTE ORB signal and trade-plan helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

from optionctl.candidates import CandidateContext, build_candidate_from_row
from optionctl.intraday import to_five_minute_bars
from optionctl.polygon import PolygonSource
from optionctl.yfinance_source import YFinanceSource

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, OptionDataSource

_ET = ZoneInfo("America/New_York")
_MARKET_OPEN = "09:30"
_ORB_END = "09:44"
_POST_ORB_START = "09:45"
_MARKET_CLOSE = "16:00"

_MIN_ORB_BARS = 5
_MIN_RSI_POINTS = 2
_RSI_MIDLINE = 50.0


class OrbDirection(StrEnum):
    """Direction labels for the ORB setup."""

    WAITING = "waiting"
    NO_TRADE = "no_trade"
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True)
class OrbSignal:
    """Structured ORB + RSI signal output for one underlying."""

    ticker: str
    signal: OrbDirection
    session_date: date
    opening_high: float
    opening_low: float
    last_price: float
    breakout_time: datetime | None
    breakout_price: float | None
    rsi_confirmed: bool | None
    reason: str


@dataclass(frozen=True)
class PositionPlan:
    """Risk-managed 0DTE position sizing plan."""

    account_size: float
    risk_pct: float
    max_risk_dollars: float
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_contract: float
    contracts: int
    notional_dollars: float
    time_stop: str
    max_trades: int


def _session_date_for_now(index_dates: list[date], now_et: datetime) -> date:
    """Pick the relevant session date for ORB calculations."""
    today = now_et.date()
    if today in index_dates:
        return today
    return max(index_dates)


def _build_signal(  # noqa: PLR0913
    *,
    ticker: str,
    signal: OrbDirection,
    session_date: date,
    opening_high: float,
    opening_low: float,
    last_price: float,
    breakout_time: datetime | None,
    breakout_price: float | None,
    rsi_confirmed: bool | None,
    reason: str,
) -> OrbSignal:
    """Create a normalized ``OrbSignal`` object."""
    return OrbSignal(
        ticker=ticker,
        signal=signal,
        session_date=session_date,
        opening_high=opening_high,
        opening_low=opening_low,
        last_price=last_price,
        breakout_time=breakout_time,
        breakout_price=breakout_price,
        rsi_confirmed=rsi_confirmed,
        reason=reason,
    )


def _opening_range_bounds(session: pd.DataFrame) -> tuple[float, float] | None:
    """Return opening-range high/low if the 9:30-9:44 window is complete."""
    opening = session.between_time(_MARKET_OPEN, _ORB_END)
    if opening.empty or len(opening) < _MIN_ORB_BARS:
        return None
    return float(opening["high"].max()), float(opening["low"].min())


def _find_breakout(
    session: pd.DataFrame, opening_high: float, opening_low: float
) -> tuple[OrbDirection, datetime | None, float | None]:
    """Find the first post-9:45 breakout beyond the opening range."""
    post_orb = session.between_time(_POST_ORB_START, _MARKET_CLOSE)
    for ts, row in post_orb.iterrows():
        ts_dt: datetime | None
        if isinstance(ts, datetime):
            ts_dt = ts
        else:
            try:
                ts_dt = datetime.fromisoformat(str(ts))
            except ValueError:
                ts_dt = None
        if ts_dt is None:
            continue

        close = float(row["close"])
        if close > opening_high:
            return OrbDirection.BULLISH, ts_dt, close
        if close < opening_low:
            return OrbDirection.BEARISH, ts_dt, close
    return OrbDirection.NO_TRADE, None, None


def _rsi_cross_confirmed(
    bars_1m: pd.DataFrame,
    *,
    breakout_time: datetime,
    direction: OrbDirection,
    eval_time: datetime,
) -> bool:
    """Check RSI(14) 5m crossover at breakout time."""
    bars_for_rsi = bars_1m[bars_1m.index <= eval_time]
    bars_5m = to_five_minute_bars(bars_for_rsi)
    if bars_5m.empty:
        return False

    rsi = compute_rsi(bars_5m["close"])
    rsi_until_breakout = rsi[rsi.index <= breakout_time]
    if len(rsi_until_breakout) < _MIN_RSI_POINTS:
        return False

    prev = float(rsi_until_breakout.iloc[-2])
    curr = float(rsi_until_breakout.iloc[-1])
    if direction == OrbDirection.BULLISH:
        return prev < _RSI_MIDLINE <= curr
    return prev > _RSI_MIDLINE >= curr


def compute_rsi(close_prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder smoothing on a price series."""
    delta = close_prices.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def evaluate_orb_signal(  # noqa: C901, PLR0911
    ticker: str,
    bars_1m: pd.DataFrame,
    *,
    now_et: datetime | None = None,
    require_rsi_confirmation: bool = True,
) -> OrbSignal:
    """Evaluate SPY-style ORB and RSI confirmation from one-minute bars.

    Args:
        ticker: Underlying symbol.
        bars_1m: One-minute OHLCV DataFrame in ET timezone.
        now_et: Override evaluation timestamp (ET) for deterministic testing.
        require_rsi_confirmation: If True, reject breakouts without RSI cross.

    Returns:
        ``OrbSignal`` with final direction and metadata.
    """
    eval_time = now_et or datetime.now(tz=_ET)
    if bars_1m.empty:
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.NO_TRADE,
            session_date=eval_time.date(),
            opening_high=0.0,
            opening_low=0.0,
            last_price=0.0,
            breakout_time=None,
            breakout_price=None,
            rsi_confirmed=None,
            reason="No intraday bars available.",
        )
    if not isinstance(bars_1m.index, pd.DatetimeIndex):
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.NO_TRADE,
            session_date=eval_time.date(),
            opening_high=0.0,
            opening_low=0.0,
            last_price=0.0,
            breakout_time=None,
            breakout_price=None,
            rsi_confirmed=None,
            reason="Intraday bars are missing a datetime index.",
        )

    index_dates: list[date | None] = []
    for value in bars_1m.index:
        if isinstance(value, datetime):
            index_dates.append(value.date())
            continue
        try:
            index_dates.append(datetime.fromisoformat(str(value)).date())
        except ValueError:
            index_dates.append(None)

    valid_dates = sorted({d for d in index_dates if d is not None})
    if not valid_dates:
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.NO_TRADE,
            session_date=eval_time.date(),
            opening_high=0.0,
            opening_low=0.0,
            last_price=0.0,
            breakout_time=None,
            breakout_price=None,
            rsi_confirmed=None,
            reason="Unable to derive session dates from intraday bars.",
        )

    session_date = _session_date_for_now(valid_dates, eval_time)
    session = bars_1m[[d == session_date for d in index_dates]]
    session = session[session.index <= eval_time]
    if session.empty:
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.NO_TRADE,
            session_date=session_date,
            opening_high=0.0,
            opening_low=0.0,
            last_price=0.0,
            breakout_time=None,
            breakout_price=None,
            rsi_confirmed=None,
            reason="No bars for the selected session.",
        )

    last_price = float(session["close"].iloc[-1])
    opening = _opening_range_bounds(session)
    if opening is None:
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.WAITING,
            session_date=session_date,
            opening_high=0.0,
            opening_low=0.0,
            last_price=last_price,
            breakout_time=None,
            breakout_price=None,
            rsi_confirmed=None,
            reason="Opening range not complete yet.",
        )

    opening_high, opening_low = opening
    direction, breakout_time, breakout_price = _find_breakout(session, opening_high, opening_low)
    if direction == OrbDirection.NO_TRADE or breakout_time is None or breakout_price is None:
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.NO_TRADE,
            session_date=session_date,
            opening_high=opening_high,
            opening_low=opening_low,
            last_price=last_price,
            breakout_time=None,
            breakout_price=None,
            rsi_confirmed=None,
            reason="No ORB breakout beyond opening range.",
        )

    rsi_confirmed = _rsi_cross_confirmed(
        bars_1m,
        breakout_time=breakout_time,
        direction=direction,
        eval_time=eval_time,
    )
    if require_rsi_confirmation and not rsi_confirmed:
        return _build_signal(
            ticker=ticker,
            signal=OrbDirection.NO_TRADE,
            session_date=session_date,
            opening_high=opening_high,
            opening_low=opening_low,
            last_price=last_price,
            breakout_time=breakout_time,
            breakout_price=breakout_price,
            rsi_confirmed=False,
            reason="Breakout occurred but RSI(14) did not confirm.",
        )

    return _build_signal(
        ticker=ticker,
        signal=direction,
        session_date=session_date,
        opening_high=opening_high,
        opening_low=opening_low,
        last_price=last_price,
        breakout_time=breakout_time,
        breakout_price=breakout_price,
        rsi_confirmed=rsi_confirmed,
        reason="ORB + RSI confirmed." if rsi_confirmed else "ORB breakout detected.",
    )


def _build_source(name: str) -> OptionDataSource:
    """Build an option data source for zero-DTE contract selection."""
    if name == "polygon":
        return PolygonSource()
    return YFinanceSource()


def _contract_price(row: dict) -> float:
    """Extract a usable contract price from ask/last fields."""
    ask = row.get("ask", 0)
    last = row.get("lastPrice", 0)
    if ask in (None, 0, 0.0):
        return float(last or 0.0)
    return float(ask)


def fetch_zero_dte_candidates(
    ticker: str,
    *,
    source_name: str = "yfinance",
    max_price: float = 5.0,
    min_volume: int = 0,
) -> list[OptionCandidate]:
    """Fetch and normalize all 0DTE contracts for a ticker.

    Args:
        ticker: Underlying symbol.
        source_name: Data source (``yfinance`` or ``polygon``).
        max_price: Maximum contract price.
        min_volume: Minimum contract volume.

    Returns:
        List of 0DTE contracts mapped into ``OptionCandidate`` objects.
    """
    source = _build_source(source_name)
    data = source.fetch_ticker_data(ticker, fetch_enhanced=False, max_dte=0)
    if data is None:
        return []

    today = datetime.now(tz=_ET).date()
    underlying_price = float(data["underlying_price"])
    candidates: list[OptionCandidate] = []

    for exp_str, chain_data in data["chains"].items():
        expiration = date.fromisoformat(exp_str)
        dte = (expiration - today).days
        if dte != 0:
            continue

        context = CandidateContext(
            expiration=expiration,
            underlying_price=underlying_price,
            dte=dte,
            days_to_earnings=data.get("days_to_earnings"),
        )

        for side_key, contract_type in (("calls", "call"), ("puts", "put")):
            for row in chain_data.get(side_key, []):
                price = _contract_price(row)
                volume = int(row.get("volume", 0) or 0)
                if price <= 0 or price > max_price or volume < min_volume:
                    continue
                row["_price"] = price
                candidates.append(
                    build_candidate_from_row(
                        ticker=ticker,
                        row=row,
                        context=context,
                        contract_type=contract_type,
                    )
                )

    return candidates


def select_directional_zero_dte(
    candidates: list[OptionCandidate],
    direction: OrbDirection,
    *,
    delta_min: float = 0.50,
    delta_max: float = 0.60,
    limit: int = 5,
) -> list[OptionCandidate]:
    """Select slightly-ITM 0DTE contracts aligned to ORB direction.

    Args:
        candidates: Candidate list from ``fetch_zero_dte_candidates``.
        direction: Target ORB direction.
        delta_min: Lower bound on absolute delta magnitude.
        delta_max: Upper bound on absolute delta magnitude.
        limit: Maximum contracts to return.

    Returns:
        Ranked contracts matching directional and delta constraints.
    """
    if direction not in (OrbDirection.BULLISH, OrbDirection.BEARISH):
        return []

    target_type = "call" if direction == OrbDirection.BULLISH else "put"
    mid_delta = (delta_min + delta_max) / 2
    target_delta = mid_delta if direction == OrbDirection.BULLISH else -mid_delta

    directional = [c for c in candidates if c.contract_type == target_type and c.dte == 0]
    if not directional:
        return []

    with_greeks: list[OptionCandidate] = []
    without_greeks: list[OptionCandidate] = []
    for c in directional:
        if c.delta is None:
            without_greeks.append(c)
            continue
        if direction == OrbDirection.BULLISH and delta_min <= c.delta <= delta_max:
            with_greeks.append(c)
        if direction == OrbDirection.BEARISH and -delta_max <= c.delta <= -delta_min:
            with_greeks.append(c)

    if with_greeks:
        ranked = sorted(
            with_greeks,
            key=lambda c: (
                abs((c.delta or target_delta) - target_delta),
                -c.volume,
                c.proximity_pct,
            ),
        )
        return ranked[:limit]

    fallback = sorted(
        without_greeks,
        key=lambda c: (c.proximity_pct, -c.volume),
    )
    return fallback[:limit]


def build_position_plan(  # noqa: PLR0913
    *,
    account_size: float,
    entry_price: float,
    risk_pct: float = 1.0,
    stop_loss_pct: float = 40.0,
    target_pct: float = 100.0,
    time_stop: str = "11:30",
    max_trades: int = 3,
) -> PositionPlan:
    """Create a position-sizing plan using fixed account-risk rules.

    Args:
        account_size: Total account equity.
        entry_price: Planned contract entry price.
        risk_pct: Percent of account to risk on one trade.
        stop_loss_pct: Stop distance as percent of entry.
        target_pct: Profit target as percent of entry.
        time_stop: Time stop (ET, HH:MM format).
        max_trades: Maximum 0DTE trades allowed for the day.

    Returns:
        ``PositionPlan`` with contract count and risk/target prices.
    """
    max_risk_dollars = account_size * (risk_pct / 100)
    stop_price = entry_price * (1 - stop_loss_pct / 100)
    target_price = entry_price * (1 + target_pct / 100)

    risk_per_contract = max(entry_price - stop_price, 0.0) * 100
    contracts = int(max_risk_dollars // risk_per_contract) if risk_per_contract > 0 else 0
    notional = contracts * entry_price * 100

    return PositionPlan(
        account_size=account_size,
        risk_pct=risk_pct,
        max_risk_dollars=max_risk_dollars,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_contract=risk_per_contract,
        contracts=contracts,
        notional_dollars=notional,
        time_stop=time_stop,
        max_trades=max_trades,
    )
