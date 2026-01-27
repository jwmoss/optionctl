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
- Two modes:
  - **Penny hunting**: far OTM $0.01 calls for lottery plays
  - **Momentum/gamma scalping**: near-the-money high-gamma contracts for scalp potential
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

## CLI Usage

### Scan for penny options

```bash
optionctl scan                          # Scan S&P 500 for $0.01 OTM calls
optionctl scan --universe volume        # Scan top stocks by volume
optionctl scan --universe watchlist --watchlist-file tickers.txt
optionctl scan --min-dte 0 --max-dte 5  # Same-week expiration only
optionctl scan --output json            # Output as JSON
```

### SPY 0DTE

```bash
optionctl spy penny                     # Find SPY 0DTE penny calls ($0.01)
optionctl spy momentum                  # Find high-gamma scalp candidates
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

## Example: Finding High-Conviction Penny Options

**Scenario**: It's a weekday and you want to find which $0.01 OTM calls have the
most volume -- contracts where a lot of people are piling in. You don't care about
proximity or IV, just raw trading activity.

```bash
$ optionctl scan --universe volume --w-vol-oi 0 --w-volume 100 --w-proximity 0 --w-iv 0 --min-volume 50
```

Sample output (Jan 26, 2026):

```
ticker,strike,expiration,ask,volume,open_interest,volume_oi_ratio,score,contract_symbol
INTC,58.0,2026-01-30,0.01,6350,5195,1.22,100.0,INTC260130C00058000
INTC,60.0,2026-01-30,0.01,2486,15503,0.16,49.7,INTC260130C00060000
INTC,59.0,2026-01-30,0.01,2409,1783,1.35,48.2,INTC260130C00059000
NVDA,215.0,2026-01-30,0.01,2193,11050,0.20,43.9,NVDA260130C00215000
INTC,69.0,2026-01-30,0.01,1553,1558,1.00,31.1,INTC260130C00069000
```

INTC dominates with 6,350 contracts on the $58 call alone. Three of the top five
are INTC, which suggests concentrated betting on an Intel move before Friday
expiration. Compare with the default balanced scoring to see if these also rank
well on proximity and IV -- if they do, that's a stronger signal.

**Follow-up**: switch to the balanced score to validate:

```bash
$ optionctl scan --universe volume --min-volume 50
```

Now the same INTC $58 call scores 23.1 (down from 100) because it's 36% OTM --
lots of people buying it, but it needs a massive move. The contracts that score
highest on balanced weights are the ones with both volume *and* a realistic
chance of hitting.

## Development

```bash
make dev       # Install all dependencies
make lint      # Run ruff + ty
make format    # Format with ruff
make test      # Run pytest
```
