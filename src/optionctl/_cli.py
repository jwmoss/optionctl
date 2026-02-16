"""The optionctl CLI entrypoint."""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

import click
from rich.console import Console
from rich.table import Table

from optionctl.models import ScoringWeights, Side

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, ScanResult
    from optionctl.zero_dte import PositionPlan

console = Console(stderr=True)

_T = TypeVar("_T")
_ProgressCallback = Callable[[str, int, int], None]

_DEFAULT_LIMIT = 20

_DEFAULT_MIN_DTE = 0
_DEFAULT_MAX_DTE = 15
_DEFAULT_MAX_PRICE = 2.00
_DEFAULT_MIN_VOLUME = 250
_DEFAULT_MIN_VOL_OI = 1.0

# Weighting tuned for unusual flow (new opening activity over legacy OI).
_UNUSUAL_WEIGHTS = ScoringWeights(
    vol_oi=55.0,
    volume=25.0,
    proximity=15.0,
    iv=5.0,
    earnings=0.0,
    vol_vs_avg=0.0,
)

# Proximity thresholds for table color coding.
_PROXIMITY_GOOD = 10
_PROXIMITY_MODERATE = 20


def _parse_side(value: str) -> Side:
    """Convert a CLI side string to a Side enum."""
    return Side(value)


def _render_table(candidates: list[OptionCandidate], title: str) -> None:
    """Render candidates as a rich table."""
    table = Table(title=title, show_lines=False)
    table.add_column("Ticker", style="cyan")
    table.add_column("C/P", justify="center")
    table.add_column("Strike", justify="right")
    table.add_column("Exp", style="green")
    table.add_column("Ask", justify="right", style="yellow")
    table.add_column("Vol", justify="right")
    table.add_column("OI", justify="right")
    table.add_column("Vol/OI", justify="right", style="magenta")
    table.add_column("IV", justify="right")
    table.add_column("Dist%", justify="right")
    table.add_column("Score", justify="right", style="bold green")

    for c in candidates:
        cp_str = "[green]C[/green]" if c.contract_type == "call" else "[red]P[/red]"

        if c.proximity_pct < _PROXIMITY_GOOD:
            dist_str = f"[bold green]{c.proximity_pct:.1f}%[/bold green]"
        elif c.proximity_pct < _PROXIMITY_MODERATE:
            dist_str = f"[yellow]{c.proximity_pct:.1f}%[/yellow]"
        else:
            dist_str = f"[red]{c.proximity_pct:.1f}%[/red]"

        table.add_row(
            c.ticker,
            cp_str,
            f"{c.strike:.2f}",
            c.expiration.isoformat(),
            f"{c.ask:.2f}",
            f"{c.volume:,}",
            f"{c.open_interest:,}",
            f"{c.volume_oi_ratio:.1f}",
            f"{c.implied_volatility:.0%}",
            dist_str,
            f"{c.score:.1f}",
        )

    console.print(table)


def _print_scan_summary(result: ScanResult) -> None:
    """Print a standard scan summary line."""
    console.print(
        f"Scanned {result.tickers_scanned} tickers, "
        f"{result.tickers_with_options} had options, "
        f"found {len(result.candidates)} unusual contracts",
    )


def _render_json(candidates: list[OptionCandidate]) -> None:
    """Render candidates as JSON."""
    data = [
        {
            "ticker": c.ticker,
            "contract_type": c.contract_type,
            "strike": c.strike,
            "expiration": c.expiration.isoformat(),
            "ask": c.ask,
            "bid": c.bid,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "volume_oi_ratio": round(c.volume_oi_ratio, 2),
            "implied_volatility": round(c.implied_volatility, 4),
            "proximity_pct": round(c.proximity_pct, 2),
            "dte": c.dte,
            "score": round(c.score, 1),
            "contract_symbol": c.contract_symbol,
        }
        for c in candidates
    ]
    print(json.dumps(data, indent=2))


def _render_csv(candidates: list[OptionCandidate]) -> None:
    """Render candidates as CSV."""
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "ticker",
            "contract_type",
            "strike",
            "expiration",
            "ask",
            "bid",
            "volume",
            "open_interest",
            "volume_oi_ratio",
            "implied_volatility",
            "proximity_pct",
            "dte",
            "score",
            "contract_symbol",
        ]
    )
    for c in candidates:
        writer.writerow(
            [
                c.ticker,
                c.contract_type,
                c.strike,
                c.expiration.isoformat(),
                c.ask,
                c.bid,
                c.volume,
                c.open_interest,
                round(c.volume_oi_ratio, 2),
                round(c.implied_volatility, 4),
                round(c.proximity_pct, 2),
                c.dte,
                round(c.score, 1),
                c.contract_symbol,
            ]
        )


def _render(
    candidates: list[OptionCandidate],
    output: str,
    title: str,
    limit: int = _DEFAULT_LIMIT,
) -> None:
    """Dispatch rendering to the appropriate format."""
    if not candidates:
        console.print("[yellow]No unusual options found.[/yellow]")
        return

    total = len(candidates)
    shown = candidates[:limit] if limit > 0 else candidates

    if output == "json":
        _render_json(shown)
    elif output == "csv":
        _render_csv(shown)
    else:
        _render_table(shown, title)

    if limit > 0 and total > limit:
        console.print(f"Showing {limit} of {total} contracts (use --all to see all)")


def _run_with_progress(
    *,
    total: int,
    task_label: str,
    description_prefix: str,
    runner: Callable[[_ProgressCallback], _T],
) -> _T:
    """Run a ticker-processing function with a shared progress bar."""
    from rich.progress import Progress

    with Progress(console=console) as progress:
        task = progress.add_task(task_label, total=total)

        def _on_progress(ticker: str, current: int, _total: int) -> None:
            progress.update(
                task, completed=current, description=f"{description_prefix} {ticker}..."
            )

        return runner(_on_progress)


def _render_zero_dte_table(candidates: list[OptionCandidate], title: str) -> None:
    """Render 0DTE contract candidates with Greeks."""
    table = Table(title=title, show_lines=False)
    table.add_column("Ticker", style="cyan")
    table.add_column("C/P", justify="center")
    table.add_column("Strike", justify="right")
    table.add_column("Ask", justify="right", style="yellow")
    table.add_column("Delta", justify="right")
    table.add_column("Gamma", justify="right")
    table.add_column("Theta", justify="right")
    table.add_column("Vega", justify="right")
    table.add_column("Vol", justify="right")
    table.add_column("OI", justify="right")
    table.add_column("Dist%", justify="right")

    for c in candidates:
        cp_str = "[green]C[/green]" if c.contract_type == "call" else "[red]P[/red]"
        table.add_row(
            c.ticker,
            cp_str,
            f"{c.strike:.2f}",
            f"{c.ask:.2f}",
            f"{c.delta:.2f}" if c.delta is not None else "-",
            f"{c.gamma:.3f}" if c.gamma is not None else "-",
            f"{c.theta:.3f}" if c.theta is not None else "-",
            f"{c.vega:.3f}" if c.vega is not None else "-",
            f"{c.volume:,}",
            f"{c.open_interest:,}",
            f"{c.proximity_pct:.1f}%",
        )

    console.print(table)


def _render_zero_dte_json(candidates: list[OptionCandidate]) -> None:
    """Render 0DTE contract candidates as JSON."""
    data = [
        {
            "ticker": c.ticker,
            "contract_type": c.contract_type,
            "strike": c.strike,
            "expiration": c.expiration.isoformat(),
            "ask": c.ask,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "delta": c.delta,
            "gamma": c.gamma,
            "theta": c.theta,
            "vega": c.vega,
            "proximity_pct": round(c.proximity_pct, 2),
            "contract_symbol": c.contract_symbol,
        }
        for c in candidates
    ]
    print(json.dumps(data, indent=2))


def _print_position_plan(plan: PositionPlan) -> None:
    """Print a compact 0DTE position-sizing plan."""
    console.print(f"Account size: ${plan.account_size:,.2f}")
    console.print(f"Risk per trade: {plan.risk_pct:.2f}% (${plan.max_risk_dollars:,.2f})")
    console.print(f"Entry: ${plan.entry_price:.2f}")
    console.print(f"Stop: ${plan.stop_price:.2f}")
    console.print(f"Target: ${plan.target_price:.2f}")
    console.print(f"Risk/contract: ${plan.risk_per_contract:,.2f}")
    console.print(f"Contracts: {plan.contracts}")
    console.print(f"Notional: ${plan.notional_dollars:,.2f}")
    console.print(f"Time stop (ET): {plan.time_stop}")
    console.print(f"Max trades/day: {plan.max_trades}")


@click.group()
@click.version_option(package_name="optionctl")
def main() -> None:
    """Unusual options flow scanner for S&P 500 tickers."""


@main.command()
@click.option(
    "--min-dte",
    type=int,
    default=_DEFAULT_MIN_DTE,
    show_default=True,
    help="Minimum days to expiration.",
)
@click.option(
    "--max-dte",
    type=int,
    default=_DEFAULT_MAX_DTE,
    show_default=True,
    help="Maximum days to expiration.",
)
@click.option(
    "--max-price",
    type=float,
    default=_DEFAULT_MAX_PRICE,
    show_default=True,
    help="Maximum ask/last price per contract.",
)
@click.option(
    "--min-volume",
    type=int,
    default=_DEFAULT_MIN_VOLUME,
    show_default=True,
    help="Minimum contract volume.",
)
@click.option(
    "--min-vol-oi",
    type=float,
    default=_DEFAULT_MIN_VOL_OI,
    show_default=True,
    help="Minimum volume/open-interest ratio.",
)
@click.option(
    "--side",
    "side_str",
    type=click.Choice(["calls", "puts", "both"]),
    default="both",
    show_default=True,
    help="Option side to scan.",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Bypass cache and fetch fresh data.",
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--limit",
    type=int,
    default=_DEFAULT_LIMIT,
    show_default=True,
    help="Maximum contracts to display.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Show all matching contracts.",
)
def scan(
    min_dte: int,
    max_dte: int,
    max_price: float,
    min_volume: int,
    min_vol_oi: float,
    side_str: str,
    refresh: bool,
    output_fmt: str,
    limit: int,
    show_all: bool,
) -> None:
    """Scan S&P 500 names for unusual options activity."""
    from optionctl.scanner import scan_universe
    from optionctl.universe import get_sp500_tickers

    tickers = get_sp500_tickers(use_cache=not refresh)
    side = _parse_side(side_str)
    console.print(f"Scanning {len(tickers)} S&P 500 tickers for unusual flow ({side_str})...")

    result = _run_with_progress(
        total=len(tickers),
        task_label="Scanning...",
        description_prefix="Scanning",
        runner=lambda on_progress: scan_universe(
            tickers,
            min_dte=min_dte,
            max_dte=max_dte,
            max_price=max_price,
            min_volume=min_volume,
            min_vol_oi=min_vol_oi,
            progress_callback=on_progress,
            weights=_UNUSUAL_WEIGHTS,
            side=side,
            use_cache=not refresh,
        ),
    )
    _print_scan_summary(result)
    _render(
        result.candidates,
        output_fmt,
        "Unusual Options Flow (S&P 500)",
        limit=0 if show_all else limit,
    )


@main.group("zero-dte")
def zero_dte() -> None:
    """ORB-based 0DTE day-trading utilities for index tickers."""


@zero_dte.command("signal")
@click.option("--ticker", type=str, default="SPY", show_default=True, help="Underlying ticker.")
@click.option(
    "--source",
    type=click.Choice(["yfinance", "polygon"]),
    default="polygon",
    show_default=True,
    help="Data source for option chains (Polygon includes Greeks).",
)
@click.option(
    "--max-price",
    type=float,
    default=5.0,
    show_default=True,
    help="Maximum contract ask/last price.",
)
@click.option(
    "--min-volume",
    type=int,
    default=100,
    show_default=True,
    help="Minimum contract volume.",
)
@click.option(
    "--delta-min",
    type=float,
    default=0.50,
    show_default=True,
    help="Minimum absolute delta for directional selection.",
)
@click.option(
    "--delta-max",
    type=float,
    default=0.60,
    show_default=True,
    help="Maximum absolute delta for directional selection.",
)
@click.option(
    "--no-rsi-confirmation",
    is_flag=True,
    default=False,
    help="Allow ORB breakouts without RSI(14) cross confirmation.",
)
@click.option(
    "--limit",
    type=int,
    default=5,
    show_default=True,
    help="Maximum contract ideas to display.",
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
    help="Output format for selected 0DTE contracts.",
)
def zero_dte_signal(
    ticker: str,
    source: str,
    max_price: float,
    min_volume: int,
    delta_min: float,
    delta_max: float,
    no_rsi_confirmation: bool,
    limit: int,
    output_fmt: str,
) -> None:
    """Generate ORB + RSI signal and shortlist directional 0DTE contracts."""
    from optionctl.intraday import fetch_intraday_bars
    from optionctl.zero_dte import (
        OrbDirection,
        evaluate_orb_signal,
        fetch_zero_dte_candidates,
        select_directional_zero_dte,
    )

    symbol = ticker.upper()
    bars_1m = fetch_intraday_bars(symbol)
    signal = evaluate_orb_signal(
        symbol,
        bars_1m,
        require_rsi_confirmation=not no_rsi_confirmation,
    )

    console.print(f"{symbol} ORB signal: [bold]{signal.signal.value}[/bold]")
    console.print(f"Session date (ET): {signal.session_date.isoformat()}")
    console.print(
        f"Opening range: {signal.opening_low:.2f} - {signal.opening_high:.2f} | "
        f"Last: {signal.last_price:.2f}"
    )
    if signal.breakout_time is not None:
        console.print(f"Breakout: {signal.breakout_time.isoformat()} @ {signal.breakout_price:.2f}")
    console.print(f"Reason: {signal.reason}")

    if signal.signal not in (OrbDirection.BULLISH, OrbDirection.BEARISH):
        return

    candidates = fetch_zero_dte_candidates(
        symbol,
        source_name=source,
        max_price=max_price,
        min_volume=min_volume,
    )
    selected = select_directional_zero_dte(
        candidates,
        signal.signal,
        delta_min=delta_min,
        delta_max=delta_max,
        limit=limit,
    )

    if not selected:
        console.print("[yellow]No matching 0DTE contracts for the signal filters.[/yellow]")
        return

    if output_fmt == "json":
        _render_zero_dte_json(selected)
    else:
        _render_zero_dte_table(
            selected,
            f"0DTE {signal.signal.value.title()} Contracts ({symbol})",
        )


@zero_dte.command("plan")
@click.option(
    "--account-size",
    type=float,
    required=True,
    help="Account size in dollars.",
)
@click.option(
    "--entry-price",
    type=float,
    required=True,
    help="Planned option entry price.",
)
@click.option(
    "--risk-pct",
    type=float,
    default=1.0,
    show_default=True,
    help="Percent of account risked per trade.",
)
@click.option(
    "--stop-loss-pct",
    type=float,
    default=40.0,
    show_default=True,
    help="Stop-loss percent from entry.",
)
@click.option(
    "--target-pct",
    type=float,
    default=100.0,
    show_default=True,
    help="Profit target percent from entry.",
)
@click.option(
    "--time-stop",
    type=str,
    default="11:30",
    show_default=True,
    help="Time stop in ET (HH:MM).",
)
@click.option(
    "--max-trades",
    type=int,
    default=3,
    show_default=True,
    help="Max number of 0DTE trades for the day.",
)
def zero_dte_plan(
    account_size: float,
    entry_price: float,
    risk_pct: float,
    stop_loss_pct: float,
    target_pct: float,
    time_stop: str,
    max_trades: int,
) -> None:
    """Build a risk-managed 0DTE position-sizing plan."""
    from optionctl.zero_dte import build_position_plan

    plan = build_position_plan(
        account_size=account_size,
        entry_price=entry_price,
        risk_pct=risk_pct,
        stop_loss_pct=stop_loss_pct,
        target_pct=target_pct,
        time_stop=time_stop,
        max_trades=max_trades,
    )
    _print_position_plan(plan)


@main.group()
def cache() -> None:
    """Manage option chain cache."""


@cache.command()
@click.option(
    "--all",
    "fetch_all",
    is_flag=True,
    default=False,
    help="Cache all expirations (not just near-term).",
)
def warm(fetch_all: bool) -> None:
    """Pre-fetch option chains for the S&P 500 universe."""
    from optionctl.scanner import warm_cache
    from optionctl.universe import get_sp500_tickers

    tickers = get_sp500_tickers()
    console.print(f"Warming cache for {len(tickers)} tickers...")

    cached = _run_with_progress(
        total=len(tickers),
        task_label="Fetching...",
        description_prefix="Fetching",
        runner=lambda on_progress: warm_cache(
            tickers,
            progress_callback=on_progress,
            max_dte=0 if fetch_all else _DEFAULT_MAX_DTE,
        ),
    )

    console.print(f"Cached {cached}/{len(tickers)} tickers")


@cache.command()
def clear() -> None:
    """Clear all cached option chain data."""
    from optionctl.cache import clear_cache

    count = clear_cache()
    console.print(f"Cleared {count} cached files")


@cache.command()
def status() -> None:
    """Show cache statistics."""
    from optionctl.cache import get_cache_stats

    stats = get_cache_stats()
    console.print(f"Cached tickers: {stats['count']}")
    console.print(f"Cache size: {stats['size_mb']} MB")
    if stats["count"] > 0 and stats["count"] <= 20:  # noqa: PLR2004
        console.print(f"Tickers: {', '.join(stats['tickers'])}")


@cache.command("prune-history")
@click.option("--max-age", type=int, default=30, help="Delete history files older than N days.")
def prune_history(max_age: int) -> None:
    """Remove old volume history files."""
    from optionctl.history import cleanup_old_history

    removed = cleanup_old_history(max_age_days=max_age)
    console.print(f"Removed {removed} old history files")
