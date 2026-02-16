# Finding High-Conviction Unusual Flow

## Scenario

You want only the strongest unusual-options signals in S&P 500 names:

- high absolute volume
- high volume/open-interest ratio
- near-term expirations

## Command

```bash
uv run optionctl scan \
  --min-dte 0 --max-dte 7 \
  --min-volume 750 \
  --min-vol-oi 2.0
```

## What to Look For

- **Vol/OI >= 2.0**: suggests more fresh positioning than roll activity.
- **Large absolute volume**: improves signal reliability and liquidity.
- **Ticker clustering**: repeated contracts on the same ticker can indicate a
  concentrated directional bet.

## Follow-Up Filter in jq

```bash
uv run optionctl scan --output json \
  | jq '[.[] | select(.volume_oi_ratio >= 3 and .volume >= 1000)]'
```
