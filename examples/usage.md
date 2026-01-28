# optionctl Usage Examples

## Installation

```bash
# Clone and install
git clone git@github.com:jwmoss/optionctl.git
cd optionctl
uv sync
```

## Running with `uv run`

All commands are run through `uv run` -- no need to activate a virtualenv.

### Basic Scan

Scan the S&P 500 for $0.01 OTM calls expiring within 14 days:

```bash
uv run optionctl scan
```

### Scan by Universe

```bash
# Top 50 high-volume stocks (faster than S&P 500)
uv run optionctl scan --universe volume

# Top 10 only
uv run optionctl scan --universe volume --top-n 10

# Custom watchlist
echo -e "AAPL\nNVDA\nTSLA\nAMD\nINTC" > tickers.txt
uv run optionctl scan --universe watchlist --watchlist-file tickers.txt
```

### Filter by Expiration

```bash
# Same-week only (0-5 DTE)
uv run optionctl scan --universe volume --min-dte 0 --max-dte 5

# Next week only
uv run optionctl scan --universe volume --min-dte 6 --max-dte 14
```

### Adjust Price and Volume Thresholds

```bash
# Find options up to $0.02 (doubles the candidate pool)
uv run optionctl scan --universe volume --max-price 0.02

# Only show contracts with 500+ volume
uv run optionctl scan --universe volume --min-volume 500
```

### Output Formats

```bash
# Rich table (default)
uv run optionctl scan --universe volume --top-n 10

# JSON (pipe to jq, save to file, etc.)
uv run optionctl scan --universe volume --top-n 10 --output json
uv run optionctl scan --universe volume --top-n 10 --output json > results.json

# CSV (open in Excel, import to Google Sheets, etc.)
uv run optionctl scan --universe volume --top-n 10 --output csv
uv run optionctl scan --universe volume --top-n 10 --output csv > results.csv
```

## SPY 0DTE

SPY has options expiring Monday, Wednesday, and Friday. These commands only
return results on those days.

### Penny Hunting

Find SPY 0DTE calls priced at $0.01:

```bash
uv run optionctl spy penny
uv run optionctl spy penny --min-volume 500
uv run optionctl spy penny --output json
```

## Custom Scoring Weights

The score is a composite of four signals. Default weights sum to 100:

| Flag | Default | Signal |
|------|---------|--------|
| `--w-vol-oi` | 30 | Volume/OI ratio (unusual activity) |
| `--w-volume` | 15 | Raw volume (liquidity + conviction) |
| `--w-proximity` | 30 | Strike proximity (chance of going ITM) |
| `--w-iv` | 25 | Implied volatility (expected move) |

### Examples

```bash
# Volume-heavy scoring (prioritize liquidity)
uv run optionctl scan --universe volume --w-vol-oi 20 --w-volume 40 --w-proximity 20 --w-iv 20

# Pure volume sort
uv run optionctl scan --universe volume --w-vol-oi 0 --w-volume 100 --w-proximity 0 --w-iv 0

# Proximity-focused (closest to the money)
uv run optionctl scan --universe volume --w-vol-oi 10 --w-volume 10 --w-proximity 60 --w-iv 20

# IV-focused (biggest expected moves)
uv run optionctl scan --universe volume --w-vol-oi 10 --w-volume 10 --w-proximity 20 --w-iv 60
```

## Combining with Other Tools

### Filter JSON with jq

```bash
# Top 5 by score
uv run optionctl scan --universe volume --output json | jq '.[0:5]'

# Only NVDA contracts
uv run optionctl scan --universe volume --output json | jq '[.[] | select(.ticker == "NVDA")]'

# Contracts with Vol/OI > 2
uv run optionctl scan --universe volume --output json | jq '[.[] | select(.volume_oi_ratio > 2)]'
```

### Save and Compare Runs

```bash
# Morning scan
uv run optionctl scan --universe volume --output json > morning.json

# Afternoon scan
uv run optionctl scan --universe volume --output json > afternoon.json

# Diff with jq
diff <(jq '.[].contract_symbol' morning.json) <(jq '.[].contract_symbol' afternoon.json)
```

## Development

```bash
# Install dev dependencies
uv sync --all-groups

# Run linter
uv run ruff format --check && uv run ruff check

# Run type checker
uv run ty check

# Run tests
uv run pytest -svv --cov=optionctl test/

# Or use Makefile shortcuts
make dev      # install everything
make lint     # ruff + ty + interrogate
make test     # pytest with coverage
make format   # auto-fix formatting
```
