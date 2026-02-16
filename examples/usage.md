# optionctl Usage Examples

## Installation

```bash
git clone git@github.com:jwmoss/optionctl.git
cd optionctl
uv sync
```

## Core Workflow (S&P 500 Unusual Flow)

```bash
uv run optionctl scan
```

This scans the full S&P 500 and ranks contracts by unusual-flow score.

## Tighten Signal Quality

```bash
# Stronger unusual activity threshold
uv run optionctl scan --min-vol-oi 2.0 --min-volume 500

# Near-term contracts only
uv run optionctl scan --min-dte 0 --max-dte 7

# Calls or puts only
uv run optionctl scan --side calls
uv run optionctl scan --side puts
```

## Output Formats

```bash
# JSON
uv run optionctl scan --output json > results.json

# CSV
uv run optionctl scan --output csv > results.csv

# Show everything (no row cap)
uv run optionctl scan --all
```

## Cache

```bash
# Warm S&P 500 chains before scan
uv run optionctl cache warm

# Force fresh data on scan
uv run optionctl scan --refresh
```

## jq Examples

```bash
# Top 10 contracts by score
uv run optionctl scan --output json | jq '.[0:10]'

# Only SPY contracts
uv run optionctl scan --output json | jq '[.[] | select(.ticker == "SPY")]'

# High conviction unusual flow
uv run optionctl scan --output json | jq '[.[] | select(.volume_oi_ratio >= 2 and .volume >= 500)]'
```
