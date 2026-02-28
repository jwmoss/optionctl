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

from optionctl.models import ScoringWeights
from optionctl.predictions import _BRIER_EXCELLENT, _BRIER_GOOD

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate, ScanResult

console = Console(stderr=True)

_T = TypeVar("_T")
_ProgressCallback = Callable[[str, int, int], None]

_DEFAULT_LIMIT = 20

_DEFAULT_MIN_DTE = 0
_DEFAULT_MAX_DTE = 15
_DEFAULT_MAX_PRICE = 0.01
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
    table.add_column("P(ITM)", justify="right")
    table.add_column("Score", justify="right", style="bold green")

    for c in candidates:
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
            f"{c.p_itm:.1%}",
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
@click.option(
    "--ticker",
    "tickers_input",
    multiple=True,
    help="Specific ticker(s) to scan (repeatable). Defaults to S&P 500.",
)
def scan(
    min_dte: int,
    max_dte: int,
    max_price: float,
    min_volume: int,
    min_vol_oi: float,
    refresh: bool,
    output_fmt: str,
    limit: int,
    show_all: bool,
    tickers_input: tuple[str, ...],
) -> None:
    """Scan for unusual options activity."""
    from optionctl.scanner import scan_universe

    if tickers_input:
        tickers = [t.upper() for t in tickers_input]
        label = ", ".join(tickers)
        title = f"Unusual Options Flow ({label})"
    else:
        from optionctl.universe import get_sp500_tickers

        tickers = get_sp500_tickers(use_cache=not refresh)
        label = "S&P 500"
        title = "Unusual Options Flow (S&P 500)"

    console.print(f"Scanning {len(tickers)} {label} tickers for unusual flow...")

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
            use_cache=not refresh,
        ),
    )
    _print_scan_summary(result)
    _render(
        result.candidates,
        output_fmt,
        title,
        limit=0 if show_all else limit,
    )


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


@main.command()
@click.option(
    "--days",
    type=int,
    default=30,
    show_default=True,
    help="Number of days to include in calibration window.",
)
def calibration(days: int) -> None:
    """Show Brier score calibration for p_itm predictions."""
    from optionctl.predictions import get_calibration_summary, resolve_outcomes

    console.print("Resolving expired predictions...")
    resolved = resolve_outcomes()
    if resolved:
        console.print(f"Resolved {resolved} predictions")

    summary = get_calibration_summary(days)

    table = Table(title=f"Calibration Summary (last {days} days)", show_lines=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    brier = summary["brier_score"]
    if brier is not None:
        if brier < _BRIER_EXCELLENT:
            interpretation = "[bold green]excellent[/bold green]"
        elif brier < _BRIER_GOOD:
            interpretation = "[yellow]good[/yellow]"
        else:
            interpretation = "[red]poor[/red]"
        table.add_row("Brier Score", f"{brier:.4f} ({interpretation})")
    else:
        table.add_row("Brier Score", "[dim]no resolved data[/dim]")

    table.add_row("Predictions", str(summary["n_predictions"]))
    table.add_row("Resolved", str(summary["n_resolved"]))
    table.add_row("Mean P(ITM)", f"{summary['mean_p_itm']:.2%}")
    table.add_row("Hit Rate", f"{summary['hit_rate']:.2%}")

    console.print(table)


@cache.command("prune-history")
@click.option("--max-age", type=int, default=30, help="Delete history files older than N days.")
def prune_history(max_age: int) -> None:
    """Remove old volume history files."""
    from optionctl.history import cleanup_old_history

    removed = cleanup_old_history(max_age_days=max_age)
    console.print(f"Removed {removed} old history files")
