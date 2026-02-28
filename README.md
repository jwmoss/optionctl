# optionctl

Opinionated CLI for finding unusual penny options activity in S&P 500 tickers — with Monte Carlo probability scoring and Brier score calibration tracking.

## What This Tool Does

`optionctl scan` sweeps all 503 S&P 500 tickers for unusual call option flow. It surfaces contracts priced at $0.01 (true penny options) with abnormal volume relative to open interest, ranks them by a composite score, and now includes a **p_itm** column: the Monte Carlo-estimated probability of expiring in-the-money.

Every scan also writes predictions to a local SQLite DB (`~/.optionctl/predictions.db`). After options expire, `optionctl calibration` resolves outcomes and computes a Brier score — so you know over time whether the signals are actually calibrated.

### Scoring signals

| Signal | Weight | Description |
|--------|--------|-------------|
| Vol/OI ratio | 25 | Unusual activity relative to open interest |
| Proximity to strike | 25 | Closer strikes score higher |
| Implied volatility | 20 | Higher IV = market expects a move |
| Raw volume | 15 | Liquidity and conviction |
| Earnings catalyst | 15 | Earnings before expiry = full points |
| p_itm (opt-in) | 0 | Monte Carlo ITM probability — enable via weights |

### p_itm: Monte Carlo probability

Each candidate's `p_itm` is estimated via Geometric Brownian Motion (50k paths, antithetic variates for ~50% variance reduction):

```
S_T = S0 × exp(-0.5 × σ² × T + σ × √T × Z)
p_itm = P(S_T > K)
```

This turns "weird volume on a $0.01 call" into an actual probability estimate.

## Defaults

```
max_price  : $0.01
min_volume : 250
min_vol_oi : 1.0
DTE        : 0–15
```

## Quick Start

```bash
uv run optionctl scan
```

Runs the full S&P 500 scan. Takes 2–3 minutes during market hours.

## Actionable Filters

For actual trade decisions, tighten the defaults:

```bash
# High-conviction filter: close to money, unusual flow, real IV
uv run optionctl scan --min-vol-oi 2.0 --min-volume 500 --max-dte 7

# Single ticker deep dive
uv run optionctl scan --ticker NVDA --ticker TSLA --refresh

# JSON / CSV for further analysis
uv run optionctl scan --output json
uv run optionctl scan --output csv
```

### What makes a good pick

A penny option worth buying should have **all** of:

- **p_itm > 1%** — Monte Carlo says there's a real chance
- **Vol/OI > 2x** — unusual flow, not noise
- **IV > 40%** — market expects a move
- **Strike within 25% of price** — not a pure lottery ticket
- **DTE ≥ 3** — gives the move time to play out

## Scan Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--min-dte` | `0` | Minimum days to expiration |
| `--max-dte` | `15` | Maximum days to expiration |
| `--max-price` | `0.01` | Max contract ask |
| `--min-volume` | `250` | Minimum contract volume |
| `--min-vol-oi` | `1.0` | Minimum volume/open-interest ratio |
| `--ticker` | S&P 500 | Specific ticker(s) to scan (repeatable) |
| `--refresh` | `false` | Bypass cache, fetch fresh data |
| `--output` | `table` | `table`, `json`, `csv` |
| `--limit` | `20` | Max rows to display |
| `--all` | `false` | Show all matching rows |

## Calibration

After options expire, resolve outcomes and check if the model is calibrated:

```bash
uv run optionctl calibration          # last 30 days
uv run optionctl calibration --days 60
```

Output includes:
- **Brier score** — `mean((p_itm - outcome)²)`. Lower is better.
  - < 0.10: excellent — trust the signal
  - 0.10–0.20: good — useful but noisy
  - \> 0.25: poor — p_itm is miscalibrated, be skeptical
- Hit rate vs mean predicted p_itm — tells you if you're over/under-estimating
- Resolved vs total predictions

## Automated Setup (OpenClaw)

Two cron jobs run automatically:

**Nightly scan — weekdays at 9 PM ET**

Runs `optionctl scan`, filters for actionable picks, and delivers to Signal:
- 🎯 **HIGH CONVICTION**: p_itm > 2%, Vol/OI > 3x, within 20% of price
- 🎲 **SPECULATIVE**: passes base filters but weaker signal
- Shows cost per contract and max loss
- No picks = no message (won't recommend garbage)

**Saturday 10 AM ET — weekly calibration report**

Runs `optionctl calibration`, resolves any expired options from the week, and delivers a Brier score + actionable sizing recommendation to Signal.

## Cache Commands

```bash
uv run optionctl cache warm           # pre-fetch S&P 500 chains
uv run optionctl cache warm --all     # all expirations
uv run optionctl cache status
uv run optionctl cache clear
uv run optionctl cache prune-history --max-age 30
```

## Development

```bash
make format
make lint
make test
```
