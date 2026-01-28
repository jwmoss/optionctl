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
    w_vol_oi: float, w_volume: float, w_proximity: float, w_iv: float
) -> ScoringWeights:
    """Build a ScoringWeights from CLI flag values."""
    from optionctl.models import ScoringWeights

    return ScoringWeights(vol_oi=w_vol_oi, volume=w_volume, proximity=w_proximity, iv=w_iv)


def _render_table(candidates: list[OptionCandidate], title: str) -> None:
    """Render candidates as a rich table."""
    table = Table(title=title, show_lines=False)
    table.add_column("Ticker", style="cyan")
    table.add_column("Strike", justify="right")
    table.add_column("Exp", style="green")
    table.add_column("Ask", justify="right", style="yellow")
    table.add_column("Bid", justify="right")
    table.add_column("Vol", justify="right")
    table.add_column("OI", justify="right")
    table.add_column("Vol/OI", justify="right", style="magenta")
    table.add_column("IV", justify="right")
    table.add_column("Dist%", justify="right")
    table.add_column("Score", justify="right", style="bold green")

    for c in candidates:
        table.add_row(
            c.ticker,
            f"{c.strike:.2f}",
            c.expiration.isoformat(),
            f"{c.ask:.2f}",
            f"{c.bid:.2f}",
            f"{c.volume:,}",
            f"{c.open_interest:,}",
            f"{c.volume_oi_ratio:.1f}",
            f"{c.implied_volatility:.1%}",
            f"{c.proximity_pct:.1f}%",
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
                round(c.score, 1),
                c.contract_symbol,
            ]
        )


def _render(
    candidates: list[OptionCandidate],
    output: str,
    title: str,
) -> None:
    """Dispatch rendering to the appropriate format."""
    if not candidates:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    if output == "json":
        _render_json(candidates)
    elif output == "csv":
        _render_csv(candidates)
    else:
        _render_table(candidates, title)


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
@click.option("--w-vol-oi", type=float, default=30.0, help="Scoring weight: volume/OI ratio.")
@click.option("--w-volume", type=float, default=15.0, help="Scoring weight: raw volume.")
@click.option("--w-proximity", type=float, default=30.0, help="Scoring weight: strike proximity.")
@click.option("--w-iv", type=float, default=25.0, help="Scoring weight: implied volatility.")
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
) -> None:
    """Scan for penny OTM call options across a stock universe."""
    from rich.progress import Progress

    from optionctl.scanner import scan_universe
    from optionctl.universe import get_tickers

    weights = _make_weights(w_vol_oi, w_volume, w_proximity, w_iv)
    tickers = get_tickers(universe, watchlist_file, top_n)
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

    _render(result.candidates, output_fmt, "Penny Option Candidates")


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
@click.option("--w-vol-oi", type=float, default=30.0, help="Scoring weight: volume/OI ratio.")
@click.option("--w-volume", type=float, default=15.0, help="Scoring weight: raw volume.")
@click.option("--w-proximity", type=float, default=30.0, help="Scoring weight: strike proximity.")
@click.option("--w-iv", type=float, default=25.0, help="Scoring weight: implied volatility.")
def penny(
    max_price: float,
    min_volume: int,
    output_fmt: str,
    w_vol_oi: float,
    w_volume: float,
    w_proximity: float,
    w_iv: float,
) -> None:
    """Find SPY 0DTE penny call options."""
    from optionctl.spy import find_penny_0dte

    weights = _make_weights(w_vol_oi, w_volume, w_proximity, w_iv)
    console.print("Scanning SPY 0DTE for penny calls...")
    candidates = find_penny_0dte(max_price, min_volume, weights)
    console.print(f"Found {len(candidates)} candidates")
    _render(candidates, output_fmt, "SPY 0DTE Penny Calls")


@spy.command()
@click.option(
    "--max-distance",
    type=float,
    default=2.0,
    help="Maximum distance from underlying (percentage).",
)
@click.option("--min-volume", type=int, default=500, help="Minimum contract volume.")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
@click.option("--w-vol-oi", type=float, default=30.0, help="Scoring weight: volume/OI ratio.")
@click.option("--w-volume", type=float, default=15.0, help="Scoring weight: raw volume.")
@click.option("--w-proximity", type=float, default=30.0, help="Scoring weight: strike proximity.")
@click.option("--w-iv", type=float, default=25.0, help="Scoring weight: implied volatility.")
def momentum(
    max_distance: float,
    min_volume: int,
    output_fmt: str,
    w_vol_oi: float,
    w_volume: float,
    w_proximity: float,
    w_iv: float,
) -> None:
    """Find SPY 0DTE near-the-money calls for momentum scalping."""
    from optionctl.spy import find_momentum_0dte

    weights = _make_weights(w_vol_oi, w_volume, w_proximity, w_iv)
    console.print("Scanning SPY 0DTE for momentum candidates...")
    candidates = find_momentum_0dte(max_distance, min_volume, weights)
    console.print(f"Found {len(candidates)} candidates")
    _render(candidates, output_fmt, "SPY 0DTE Momentum Candidates")
