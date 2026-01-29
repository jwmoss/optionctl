"""The optionctl CLI entrypoint."""

from __future__ import annotations

import csv
import json
import sys
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, ScoringWeights

console = Console(stderr=True)


def _make_weights(
    w_vol_oi: float,
    w_volume: float,
    w_proximity: float,
    w_iv: float,
    w_earnings: float = 15.0,
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

# Proximity thresholds for color coding (lower = closer to money = better)
_PROXIMITY_GOOD = 15  # Green: < 15% from strike
_PROXIMITY_MODERATE = 35  # Yellow: 15-35% from strike, Red: > 35%


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
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
@click.option("--w-vol-oi", type=float, default=25.0, help="Scoring weight: volume/OI ratio.")
@click.option("--w-volume", type=float, default=15.0, help="Scoring weight: raw volume.")
@click.option("--w-proximity", type=float, default=25.0, help="Scoring weight: strike proximity.")
@click.option("--w-iv", type=float, default=20.0, help="Scoring weight: implied volatility.")
@click.option("--w-earnings", type=float, default=15.0, help="Scoring weight: earnings catalyst.")
@click.option(
    "--refresh", is_flag=True, default=False, help="Bypass ticker cache and fetch fresh data."
)
@click.option("--limit", type=int, default=_DEFAULT_LIMIT, help="Max candidates to display.")
@click.option("--all", "show_all", is_flag=True, default=False, help="Show all candidates.")
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
    from rich.progress import Progress

    from optionctl.scanner import scan_universe
    from optionctl.universe import get_tickers

    weights = _make_weights(w_vol_oi, w_volume, w_proximity, w_iv, w_earnings)
    tickers = get_tickers(universe, watchlist_file, top_n, use_cache=not refresh)
    console.print(f"Scanning {len(tickers)} tickers ({universe})...")

    with Progress(console=console) as progress:
        task = progress.add_task("Scanning...", total=len(tickers))

        def on_progress(ticker: str, current: int, total: int) -> None:
            progress.update(task, completed=current, description=f"Scanning {ticker}...")

        result = scan_universe(
            tickers,
            min_dte,
            max_dte,
            max_price,
            min_volume,
            progress_callback=on_progress,
            weights=weights,
        )

    console.print(
        f"Scanned {result.tickers_scanned} tickers, "
        f"{result.tickers_with_options} had options, "
        f"found {len(result.candidates)} candidates",
    )

    _render(
        result.candidates, output_fmt, "Penny Option Candidates", limit=0 if show_all else limit
    )


@main.group()
def spy() -> None:
    """SPY 0DTE options scanner."""


@spy.command()
@click.option("--max-price", type=float, default=0.01, help="Maximum ask price.")
@click.option("--min-volume", type=int, default=100, help="Minimum contract volume.")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
@click.option("--w-vol-oi", type=float, default=25.0, help="Scoring weight: volume/OI ratio.")
@click.option("--w-volume", type=float, default=15.0, help="Scoring weight: raw volume.")
@click.option("--w-proximity", type=float, default=25.0, help="Scoring weight: strike proximity.")
@click.option("--w-iv", type=float, default=20.0, help="Scoring weight: implied volatility.")
@click.option("--limit", type=int, default=_DEFAULT_LIMIT, help="Max candidates to display.")
@click.option("--all", "show_all", is_flag=True, default=False, help="Show all candidates.")
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
@click.option("--top", type=int, default=5, help="Number of candidates to show from each scan.")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
def favorites(top: int, output_fmt: str) -> None:
    """Run favorite scans: S&P 500 (balanced) + high-volume stocks (by volume)."""
    from rich.progress import Progress

    from optionctl.scanner import scan_universe
    from optionctl.universe import get_sp500_tickers, get_top_volume_tickers

    # S&P 500 scan with balanced weights including earnings
    sp500_weights = _make_weights(w_vol_oi=25, w_volume=15, w_proximity=25, w_iv=20, w_earnings=15)
    sp500_tickers = get_sp500_tickers()
    console.print(f"Scanning {len(sp500_tickers)} S&P 500 tickers...")

    with Progress(console=console) as progress:
        task = progress.add_task("Scanning...", total=len(sp500_tickers))

        def on_sp500_progress(ticker: str, current: int, total: int) -> None:
            progress.update(task, completed=current, description=f"Scanning {ticker}...")

        sp500_result = scan_universe(
            sp500_tickers,
            min_dte=0,
            max_dte=5,
            max_price=0.01,
            min_volume=100,
            progress_callback=on_sp500_progress,
            weights=sp500_weights,
        )

    console.print(
        f"Scanned {sp500_result.tickers_scanned} tickers, "
        f"{sp500_result.tickers_with_options} had options, "
        f"found {len(sp500_result.candidates)} candidates",
    )
    _render(sp500_result.candidates, output_fmt, "S&P 500 (balanced, max 5 DTE)", limit=top)

    console.print()

    # High-volume stocks scan with volume-focused weights
    volume_weights = _make_weights(w_vol_oi=0, w_volume=100, w_proximity=0, w_iv=0, w_earnings=0)
    volume_tickers = get_top_volume_tickers(50)
    console.print(f"Scanning {len(volume_tickers)} high-volume tickers...")

    with Progress(console=console) as progress:
        task = progress.add_task("Scanning...", total=len(volume_tickers))

        def on_volume_progress(ticker: str, current: int, total: int) -> None:
            progress.update(task, completed=current, description=f"Scanning {ticker}...")

        volume_result = scan_universe(
            volume_tickers,
            min_dte=0,
            max_dte=14,
            max_price=0.01,
            min_volume=50,
            progress_callback=on_volume_progress,
            weights=volume_weights,
        )

    console.print(
        f"Scanned {volume_result.tickers_scanned} tickers, "
        f"{volume_result.tickers_with_options} had options, "
        f"found {len(volume_result.candidates)} candidates",
    )
    _render(volume_result.candidates, output_fmt, "High-Volume (by volume)", limit=top)
