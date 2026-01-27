# Scanning a Custom Watchlist

## Scenario

You have a specific set of tickers you follow -- maybe earnings plays, sector
bets, or stocks with upcoming catalysts. You want to scan just those tickers
for penny options.

## Setup

Create a watchlist file with one ticker per line. Lines starting with `#` are
comments:

```bash
cat > my_watchlist.txt << 'EOF'
# Earnings this week
MSFT
TSLA
META

# Semiconductor plays
NVDA
AMD
INTC
MU

# Speculative
MARA
RIOT
COIN
EOF
```

## Command

```bash
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt
```

With additional filters:

```bash
# Same-week expiration only
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt \
  --min-dte 0 --max-dte 5

# Contracts up to $0.05 with 200+ volume
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt \
  --max-price 0.05 --min-volume 200

# Save results as CSV
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt \
  --output csv > results.csv
```

## Combining with jq

```bash
# Find contracts with Vol/OI > 2 (strong unusual activity signal)
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt \
  --output json | jq '[.[] | select(.volume_oi_ratio > 2)]'

# Group results by ticker
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt \
  --output json | jq 'group_by(.ticker) | map({ticker: .[0].ticker, count: length})'

# Show only ticker, strike, volume, and score
uv run optionctl scan --universe watchlist --watchlist-file my_watchlist.txt \
  --output json | jq '.[] | {ticker, strike, volume, score}'
```

## Pre-Earnings Scan

Stocks with earnings announcements often have elevated IV on their options,
which can inflate penny option premiums from $0.01 to $0.02+ even without a
move in the underlying. Scan your earnings watchlist a day or two before the
report:

```bash
# IV-focused scoring for pre-earnings
uv run optionctl scan --universe watchlist --watchlist-file earnings.txt \
  --w-vol-oi 15 --w-volume 15 --w-proximity 20 --w-iv 50
```
