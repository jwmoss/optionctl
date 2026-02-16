# optionctl

Opinionated CLI for finding unusual options activity in S&P 500 tickers.

## What This Tool Does

`optionctl` scans all S&P 500 tickers by default.

It ranks contracts using an unusual-flow score weighted toward:

- `Vol/OI` (new opening activity signal)
- raw contract volume
- distance to the underlying (proximity)
- IV (small weight)

## Defaults (Opinionated)

The default scan is tuned for unusual flow, not penny-option lottery tickets:

- `max_price`: `2.00`
- `min_volume`: `250`
- `min_vol_oi`: `1.0`
- `DTE`: `0-15`

## Quick Start

```bash
uv run optionctl scan
```

This runs the default unusual-flow scan across the full S&P 500 universe.

## Common Commands

```bash
# Tighten unusual threshold
uv run optionctl scan --min-vol-oi 2.0 --min-volume 500

# JSON / CSV output
uv run optionctl scan --output json
uv run optionctl scan --output csv
```

## Scan Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--min-dte` | `0` | Minimum days to expiration |
| `--max-dte` | `15` | Maximum days to expiration |
| `--max-price` | `2.00` | Max contract ask/last |
| `--min-volume` | `250` | Minimum contract volume |
| `--min-vol-oi` | `1.0` | Minimum volume/open-interest ratio |
| `--output` | `table` | `table`, `json`, `csv` |
| `--limit` | `20` | Max rows to display |
| `--all` | `false` | Show all rows |
| `--refresh` | `false` | Bypass chain cache |

## Cache Commands

```bash
# Warm S&P 500 universe
uv run optionctl cache warm

# Warm all expirations
uv run optionctl cache warm --all

# Inspect / clear cache
uv run optionctl cache status
uv run optionctl cache clear

# Prune volume-history files
uv run optionctl cache prune-history --max-age 30
```

## Development

```bash
make format
make lint
make test
```
