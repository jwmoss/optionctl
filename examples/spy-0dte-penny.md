# SPY 0DTE Penny Hunting

## Scenario

It's a Monday, Wednesday, or Friday and you want to find SPY options expiring
today that are priced at $0.01. These are far OTM lottery tickets -- if SPY
makes a sudden move in your direction, a $0.01 contract can go to $0.05+ fast.

## Command

```bash
uv run optionctl spy penny
```

With custom thresholds:

```bash
# Only show contracts with 500+ volume for better liquidity
uv run optionctl spy penny --min-volume 500

# Look for contracts up to $0.02
uv run optionctl spy penny --max-price 0.02

# JSON output for piping to jq
uv run optionctl spy penny --output json
```

## What to Look For

- **Volume**: Higher volume means you can actually get filled. Avoid contracts
  with single-digit volume.
- **Vol/OI ratio > 1.0**: More contracts traded today than exist in open
  interest. Someone is opening new positions, not closing old ones.
- **Proximity**: A $0.01 call that's only 1-2% OTM is much more likely to
  double than one that's 5%+ OTM. SPY moves of 1-2% happen regularly.

## When to Run

- **Best windows**: 9:30-10:30 AM ET (opening volatility) and 3:30-4:00 PM ET
  (closing moves).
- **Only works on M/W/F**: SPY 0DTE expirations are Monday, Wednesday, Friday.
  Running this on other days will return no candidates.

## Risk

These contracts expire worthless the vast majority of the time. Never risk more
than you can afford to lose. A common approach is to allocate a fixed small
dollar amount (e.g., $50-100) per day and treat it as a cost of playing.
