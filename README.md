# optionctl

A Python CLI tool to find stock options on high-volume stocks priced at $0.01 with potential to increase to $0.02 or higher. Also supports SPY 0DTE scanning.

## Strategy

### Penny Options ($0.01 OTM Calls)

- Target deep OTM calls near expiration (0-14 DTE) on high-volume stocks
- The edge comes from finding contracts with **unusual volume/OI ratios** (signals smart money), **proximity to strike** (closer = more likely to double), and **IV spikes** (catalyst expected)
- A 100% return ($0.01 -> $0.02) requires a relatively small move in the underlying
- Key risk: vast majority expire worthless -- this is a numbers game

### SPY 0DTE

- SPY has M/W/F expirations with massive liquidity
- **Penny hunting**: far OTM $0.01 calls for lottery plays
- Best windows: 9:30-10:30 AM ET and 3:30-4:00 PM ET

### Filtering Criteria

| Signal | Default Weight | Description |
|--------|---------------|-------------|
| Volume/OI ratio | 30 | High volume relative to open interest signals unusual activity / new positions |
| Raw volume | 15 | High absolute volume means liquidity and stronger conviction |
| Proximity to strike | 30 | How close the underlying is to the strike -- closer = higher chance of going ITM |
| Implied volatility | 25 | High IV suggests expected move / catalyst |

All four signals are combined into a configurable composite score to rank candidates.

### Data Source

Yahoo Finance via `yfinance` (free, sufficient for scanning). Live data managed separately.

## Architecture

```
src/optionctl/
├── __init__.py
├── cli.py              # CLI entry point
├── scanner.py           # Core scanning engine
├── filters.py           # Volume/OI, proximity, IV filters
├── scoring.py           # Composite scoring of candidates
├── universe.py          # Stock universe providers (S&P500, top volume, watchlist)
├── spy.py               # SPY 0DTE specific logic
└── models.py            # Data models (dataclasses)
```

## Quick Start

These are the go-to scans:

```bash
# S&P 500 penny options expiring this week
uv run optionctl scan --universe sp500 --max-dte 5

# High-volume stocks ranked purely by raw volume, lower volume floor
uv run optionctl scan --universe volume \
  --w-vol-oi 0 --w-volume 100 --w-proximity 0 --w-iv 0 \
  --min-volume 50
```

## CLI Usage

### Scan for penny options

```bash
optionctl scan                          # Scan S&P 500 for $0.01 OTM calls
optionctl scan --universe sp500 --max-dte 5  # S&P 500, same-week only
optionctl scan --universe volume        # Scan top stocks by volume
optionctl scan --universe watchlist --watchlist-file tickers.txt
optionctl scan --min-dte 0 --max-dte 5  # Same-week expiration only
optionctl scan --output json            # Output as JSON
```

### SPY 0DTE

```bash
optionctl spy penny                     # Find SPY 0DTE penny calls ($0.01)
```

### Custom Scoring Weights

All weights are tunable via CLI flags. They default to summing to 100:

```bash
optionctl scan --w-vol-oi 30 --w-volume 15 --w-proximity 30 --w-iv 25  # defaults
optionctl scan --w-vol-oi 0 --w-volume 100 --w-proximity 0 --w-iv 0    # pure volume
optionctl scan --w-vol-oi 10 --w-volume 10 --w-proximity 60 --w-iv 20  # proximity-focused
```

### Common Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--universe` | `sp500` | Stock universe: `sp500`, `volume`, `watchlist` |
| `--min-dte` | `0` | Minimum days to expiration |
| `--max-dte` | `14` | Maximum days to expiration |
| `--watchlist-file` | - | Path to file with ticker symbols (one per line) |
| `--min-volume` | `100` | Minimum contract volume |
| `--output` | `table` | Output format: `table`, `json`, `csv` |
| `--w-vol-oi` | `30` | Scoring weight: volume/OI ratio |
| `--w-volume` | `15` | Scoring weight: raw volume |
| `--w-proximity` | `30` | Scoring weight: strike proximity |
| `--w-iv` | `25` | Scoring weight: implied volatility |

## Examples

See the [examples/](examples/) directory for detailed walkthroughs:

- **[High-Conviction Volume Scan](examples/high-conviction-volume.md)** -- Find penny options with the most raw trading activity using pure volume scoring
- **[SPY 0DTE Penny Hunting](examples/spy-0dte-penny.md)** -- Find $0.01 SPY calls expiring today for lottery plays
- **[Custom Watchlist](examples/custom-watchlist.md)** -- Scan a specific set of tickers, including pre-earnings plays
- **[General Usage](examples/usage.md)** -- Full reference for all commands, flags, output formats, and `jq` recipes

## Development

```bash
make dev       # Install all dependencies
make lint      # Run ruff + ty
make format    # Format with ruff
make test      # Run pytest
```
