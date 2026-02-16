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

from optionctl.models import (
    DEFAULT_WEIGHT_EARNINGS,
    DEFAULT_WEIGHT_IV,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_VOL_OI,
    DEFAULT_WEIGHT_VOLUME,
)

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, ScanResult, ScoringWeights

console = Console(stderr=True)

_T = TypeVar("_T")
_ProgressCallback = Callable[[str, int, int], None]
_ClickDecorator = Callable[[Callable[..., object]], Callable[..., object]]


def _apply_click_options(*options: _ClickDecorator) -> _ClickDecorator:
    """Apply click options in declaration order."""

    def _decorator(func: Callable[..., object]) -> Callable[..., object]:
        for option in reversed(options):
            func = option(func)
        return func

    return _decorator


def _make_weights(
    w_vol_oi: float,
    w_volume: float,
    w_proximity: float,
    w_iv: float,
    w_earnings: float = DEFAULT_WEIGHT_EARNINGS,
) -> ScoringWeights:
    """Build a ScoringWeights from CLI flag values."""
    from optionctl.models import ScoringWeights

    return ScoringWeights(
        vol_oi=w_vol_oi,
        volume=w_volume,
        proximity=w_proximity,
        iv=w_iv,
        earnings=w_earnings,
    )


def _render_table(candidates: list[OptionCandidate], title: str) -> None:
    """Render candidates as a rich table."""
    table = Table(title=title, show_lines=False)
    table.add_column("Ticker", style="cyan")
    table.add_column("Strike", justify="right")
    table.add_column("Exp", style="green")
    table.add_column("Ask", justify="right", style="yellow")
    table.add_column("Vol", justify="right")
    table.add_column("OI", justify="right")
    table.add_column("Vol/OI", justify="right", style="magenta")
    table.add_column("IV", justify="right")
    table.add_column("Dist%", justify="right")
    table.add_column("Earn", justify="right", style="yellow")
    table.add_column("Score", justify="right", style="bold green")

    for c in candidates:
        # Format earnings display
        if c.days_to_earnings is not None:
            if 0 <= c.days_to_earnings <= c.dte:
                earn_str = f"[bold red]{c.days_to_earnings}d![/bold red]"
            else:
                earn_str = f"{c.days_to_earnings}d"
        else:
            earn_str = "-"

        # Format proximity/distance display (lower = closer to money = better)
        if c.proximity_pct < _PROXIMITY_GOOD:
            dist_str = f"[bold green]{c.proximity_pct:.1f}%[/bold green]"
        elif c.proximity_pct < _PROXIMITY_MODERATE:
            dist_str = f"[yellow]{c.proximity_pct:.1f}%[/yellow]"
        else:
            dist_str = f"[red]{c.proximity_pct:.1f}%[/red]"

        table.add_row(
            c.ticker,
            f"{c.strike:.2f}",
            c.expiration.isoformat(),
            f"{c.ask:.2f}",
            f"{c.volume:,}",
            f"{c.open_interest:,}",
            f"{c.volume_oi_ratio:.1f}",
            f"{c.implied_volatility:.0%}",
            dist_str,
            earn_str,
            f"{c.score:.1f}",
        )

    console.print(table)


def _print_scan_summary(result: ScanResult) -> None:
    """Print a standard scan summary line."""
    console.print(
        f"Scanned {result.tickers_scanned} tickers, "
        f"{result.tickers_with_options} had options, "
        f"found {len(result.candidates)} candidates",
    )


def _render_json(candidates: list[OptionCandidate]) -> None:
    """Render candidates as JSON."""
    data = [
        {
            "ticker": c.ticker,
            "strike": c.strike,
            "expiration": c.expiration.isoformat(),
            "ask": c.ask,
            "bid": c.bid,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "volume_oi_ratio": round(c.volume_oi_ratio, 2),
            "implied_volatility": round(c.implied_volatility, 4),
            "proximity_pct": round(c.proximity_pct, 2),
            "days_to_earnings": c.days_to_earnings,
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
            "strike",
            "expiration",
            "ask",
            "bid",
            "volume",
            "open_interest",
            "volume_oi_ratio",
            "implied_volatility",
            "proximity_pct",
            "days_to_earnings",
            "dte",
            "score",
            "contract_symbol",
        ]
    )
    for c in candidates:
        writer.writerow(
            [
                c.ticker,
                c.strike,
                c.expiration.isoformat(),
                c.ask,
                c.bid,
                c.volume,
                c.open_interest,
                round(c.volume_oi_ratio, 2),
                round(c.implied_volatility, 4),
                round(c.proximity_pct, 2),
                c.days_to_earnings if c.days_to_earnings is not None else "",
                c.dte,
                round(c.score, 1),
                c.contract_symbol,
            ]
        )


_DEFAULT_LIMIT = 20

# Proximity thresholds for color coding (aligned with scoring logic)
_PROXIMITY_GOOD = 10  # Green: < 10% (most proximity points)
_PROXIMITY_MODERATE = 20  # Yellow: 10-20% (partial points), Red: > 20% (zero points)


def _render(
    candidates: list[OptionCandidate],
    output: str,
    title: str,
    limit: int = _DEFAULT_LIMIT,
) -> None:
    """Dispatch rendering to the appropriate format."""
    if not candidates:
        console.print("[yellow]No candidates found.[/yellow]")
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
        console.print(f"Showing {limit} of {total} candidates (use --all to see all)")


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


_OUTPUT_OPTION = click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
_LIMIT_OPTION = click.option(
    "--limit", type=int, default=_DEFAULT_LIMIT, help="Max candidates to display."
)
_ALL_OPTION = click.option(
    "--all", "show_all", is_flag=True, default=False, help="Show all candidates."
)
_W_VOL_OI_OPTION = click.option(
    "--w-vol-oi",
    type=float,
    default=DEFAULT_WEIGHT_VOL_OI,
    help="Scoring weight: volume/OI ratio.",
)
_W_VOLUME_OPTION = click.option(
    "--w-volume",
    type=float,
    default=DEFAULT_WEIGHT_VOLUME,
    help="Scoring weight: raw volume.",
)
_W_PROXIMITY_OPTION = click.option(
    "--w-proximity",
    type=float,
    default=DEFAULT_WEIGHT_PROXIMITY,
    help="Scoring weight: strike proximity.",
)
_W_IV_OPTION = click.option(
    "--w-iv",
    type=float,
    default=DEFAULT_WEIGHT_IV,
    help="Scoring weight: implied volatility.",
)
_W_EARNINGS_OPTION = click.option(
    "--w-earnings",
    type=float,
    default=DEFAULT_WEIGHT_EARNINGS,
    help="Scoring weight: earnings catalyst.",
)


@click.group()
@click.version_option(package_name="optionctl")
def main() -> None:
    """Penny options scanner for high-volume stocks and SPY 0DTE."""


@main.command()
@click.option(
    "--universe",
    type=click.Choice(["sp500", "volume", "watchlist"]),
    default="sp500",
    help="Stock universe to scan.",
)
@click.option("--watchlist-file", type=click.Path(exists=True), default=None)
@click.option("--top-n", type=int, default=50, help="Number of tickers for volume universe.")
@click.option("--min-dte", type=int, default=0, help="Minimum days to expiration.")
@click.option("--max-dte", type=int, default=14, help="Maximum days to expiration.")
@click.option("--max-price", type=float, default=0.01, help="Maximum ask price.")
@click.option("--min-volume", type=int, default=100, help="Minimum contract volume.")
@click.option(
    "--refresh", is_flag=True, default=False, help="Bypass ticker cache and fetch fresh data."
)
@_apply_click_options(
    _OUTPUT_OPTION,
    _W_VOL_OI_OPTION,
    _W_VOLUME_OPTION,
    _W_PROXIMITY_OPTION,
    _W_IV_OPTION,
    _W_EARNINGS_OPTION,
    _LIMIT_OPTION,
    _ALL_OPTION,
)
def scan(
    universe: str,
    watchlist_file: str | None,
    top_n: int,
    min_dte: int,
    max_dte: int,
    max_price: float,
    min_volume: int,
    output_fmt: str,
    w_vol_oi: float,
    w_volume: float,
    w_proximity: float,
    w_iv: float,
    w_earnings: float,
    refresh: bool,
    limit: int,
    show_all: bool,
) -> None:
    """Scan for penny OTM call options across a stock universe."""
    from optionctl.scanner import scan_universe
    from optionctl.universe import get_tickers

    weights = _make_weights(w_vol_oi, w_volume, w_proximity, w_iv, w_earnings)
    tickers = get_tickers(universe, watchlist_file, top_n, use_cache=not refresh)
    console.print(f"Scanning {len(tickers)} tickers ({universe})...")

    result = _run_with_progress(
        total=len(tickers),
        task_label="Scanning...",
        description_prefix="Scanning",
        runner=lambda on_progress: scan_universe(
            tickers,
            min_dte,
            max_dte,
            max_price,
            min_volume,
            progress_callback=on_progress,
            weights=weights,
            use_cache=not refresh,
        ),
    )
    _print_scan_summary(result)

    _render(
        result.candidates, output_fmt, "Penny Option Candidates", limit=0 if show_all else limit
    )


@main.group()
def spy() -> None:
    """SPY 0DTE options scanner."""


@spy.command()
@click.option("--max-price", type=float, default=0.01, help="Maximum ask price.")
@click.option("--min-volume", type=int, default=100, help="Minimum contract volume.")
@_apply_click_options(
    _OUTPUT_OPTION,
    _W_VOL_OI_OPTION,
    _W_VOLUME_OPTION,
    _W_PROXIMITY_OPTION,
    _W_IV_OPTION,
    _LIMIT_OPTION,
    _ALL_OPTION,
)
def penny(
    max_price: float,
    min_volume: int,
    output_fmt: str,
    w_vol_oi: float,
    w_volume: float,
    w_proximity: float,
    w_iv: float,
    limit: int,
    show_all: bool,
) -> None:
    """Find SPY 0DTE penny call options."""
    from optionctl.spy import find_penny_0dte

    weights = _make_weights(w_vol_oi, w_volume, w_proximity, w_iv, w_earnings=0)
    console.print("Scanning SPY 0DTE for penny calls...")
    candidates = find_penny_0dte(max_price, min_volume, weights)
    console.print(f"Found {len(candidates)} candidates")
    _render(candidates, output_fmt, "SPY 0DTE Penny Calls", limit=0 if show_all else limit)


@main.command()
@click.option("--top", type=int, default=10, help="Number of candidates to show from each scan.")
@click.option("--days", type=int, default=7, help="Maximum days to expiration.")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
def favorites(top: int, days: int, output_fmt: str) -> None:
    """Run favorite scans: S&P 500 (balanced) + high-volume stocks (by volume)."""
    from optionctl.scanner import scan_universe
    from optionctl.universe import get_sp500_tickers, get_top_volume_tickers

    # S&P 500 scan with balanced weights including earnings
    sp500_weights = _make_weights(
        w_vol_oi=DEFAULT_WEIGHT_VOL_OI,
        w_volume=DEFAULT_WEIGHT_VOLUME,
        w_proximity=DEFAULT_WEIGHT_PROXIMITY,
        w_iv=DEFAULT_WEIGHT_IV,
        w_earnings=DEFAULT_WEIGHT_EARNINGS,
    )
    sp500_tickers = get_sp500_tickers()
    console.print(f"Scanning {len(sp500_tickers)} S&P 500 tickers...")

    sp500_result = _run_with_progress(
        total=len(sp500_tickers),
        task_label="Scanning...",
        description_prefix="Scanning",
        runner=lambda on_progress: scan_universe(
            sp500_tickers,
            min_dte=1,
            max_dte=days,
            max_price=0.01,
            min_volume=100,
            progress_callback=on_progress,
            weights=sp500_weights,
        ),
    )
    _print_scan_summary(sp500_result)
    _render(sp500_result.candidates, output_fmt, f"S&P 500 (balanced, max {days} DTE)", limit=top)

    console.print()

    # High-volume stocks scan with volume-focused weights
    volume_weights = _make_weights(w_vol_oi=0, w_volume=100, w_proximity=0, w_iv=0, w_earnings=0)
    volume_tickers = get_top_volume_tickers(50)
    console.print(f"Scanning {len(volume_tickers)} high-volume tickers...")

    volume_result = _run_with_progress(
        total=len(volume_tickers),
        task_label="Scanning...",
        description_prefix="Scanning",
        runner=lambda on_progress: scan_universe(
            volume_tickers,
            min_dte=1,
            max_dte=days,
            max_price=0.01,
            min_volume=50,
            progress_callback=on_progress,
            weights=volume_weights,
        ),
    )
    _print_scan_summary(volume_result)
    _render(volume_result.candidates, output_fmt, f"High-Volume (max {days} DTE)", limit=top)


# ---------------------------------------------------------------------------
# Cache management commands
# ---------------------------------------------------------------------------


@main.group()
def cache() -> None:
    """Manage the option chain cache."""


@cache.command()
@click.option(
    "--universe",
    type=click.Choice(["sp500", "volume"]),
    default="sp500",
    help="Universe to warm cache for.",
)
@click.option(
    "--all",
    "fetch_all",
    is_flag=True,
    default=False,
    help="Cache all expirations (not just 2 weeks).",
)
def warm(universe: str, *, fetch_all: bool) -> None:
    """Pre-fetch and cache option chains for a universe."""
    from optionctl.scanner import warm_cache
    from optionctl.universe import get_sp500_tickers, get_top_volume_tickers

    tickers = get_sp500_tickers() if universe == "sp500" else get_top_volume_tickers(50)

    console.print(f"Warming cache for {len(tickers)} tickers...")

    cached = _run_with_progress(
        total=len(tickers),
        task_label="Fetching...",
        description_prefix="Fetching",
        runner=lambda on_progress: warm_cache(
            tickers,
            progress_callback=on_progress,
            max_dte=0 if fetch_all else 14,
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
