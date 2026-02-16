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
- `side`: `both`
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

# Calls only, next 15 days
uv run optionctl scan --side calls --min-dte 0 --max-dte 15

# JSON / CSV output
uv run optionctl scan --output json
uv run optionctl scan --output csv
```

## 0DTE ORB Commands

```bash
# ORB + RSI signal for SPY with 0DTE contract ideas
uv run optionctl zero-dte signal --ticker SPY --source polygon

# Build a risk-managed position plan
uv run optionctl zero-dte plan \
  --account-size 25000 \
  --entry-price 1.50 \
  --risk-pct 1.2
```

Optional penny-contract override:

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --max-price 0.01 \
  --delta-min 0.01 \
  --delta-max 0.20
```

## Scan Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--min-dte` | `0` | Minimum days to expiration |
| `--max-dte` | `15` | Maximum days to expiration |
| `--max-price` | `2.00` | Max contract ask/last |
| `--min-volume` | `250` | Minimum contract volume |
| `--min-vol-oi` | `1.0` | Minimum volume/open-interest ratio |
| `--side` | `both` | `calls`, `puts`, or `both` |
| `--output` | `table` | `table`, `json`, `csv` |
| `--limit` | `20` | Max rows to display |
| `--all` | `false` | Show all rows |
| `--refresh` | `false` | Bypass chain cache |

## 0DTE Flags

`zero-dte signal`:

| Flag | Default | Purpose |
|------|---------|---------|
| `--ticker` | `SPY` | Underlying symbol |
| `--source` | `polygon` | Chain source (`polygon` includes Greeks) |
| `--max-price` | `5.0` | Max contract ask/last |
| `--min-volume` | `100` | Minimum contract volume |
| `--delta-min` | `0.50` | Lower bound on absolute delta |
| `--delta-max` | `0.60` | Upper bound on absolute delta |
| `--no-rsi-confirmation` | `false` | Allow breakouts without RSI cross |
| `--limit` | `5` | Max contracts to return |
| `--output` | `table` | `table`, `json` |

`zero-dte plan`:

| Flag | Default | Purpose |
|------|---------|---------|
| `--account-size` | required | Account equity in dollars |
| `--entry-price` | required | Planned option entry price |
| `--risk-pct` | `1.0` | Risk % per trade |
| `--stop-loss-pct` | `40.0` | Stop distance from entry |
| `--target-pct` | `100.0` | Profit target from entry |
| `--time-stop` | `11:30` | Time stop in ET |
| `--max-trades` | `3` | Daily max trade count |

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

## Examples

- `examples/usage.md` — core S&P 500 unusual-flow scans.
- `examples/high-conviction-volume.md` — tighter unusual-flow thresholds.
- `examples/zero-dte-day-trading.md` — timed daily 0DTE playbook (night-before to post-close).
- `examples/zero-dte-orb-scenarios.md` — concrete "if X happens, do Y" trade scenarios.
- `examples/zero-dte-orb-scenarios-penny.md` — `$0.01` penny-contract ORB scenarios.
- `examples/zero-dte-day-trading.sh` — phase-based helper (`night-before`, `signal`, `plan`).
