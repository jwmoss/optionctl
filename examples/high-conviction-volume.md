# Finding High-Conviction Penny Options by Volume

## Scenario

You want to find which $0.01 OTM calls have the most raw trading activity.
You don't care about proximity or IV -- just where the volume is.

## Command

```bash
uv run optionctl scan --universe volume \
  --w-vol-oi 0 --w-volume 100 --w-proximity 0 --w-iv 0 \
  --min-volume 50
```

## Sample Output (Jan 26, 2026)

```
ticker  strike  expiration  ask   volume  open_interest  vol/oi  score
INTC    58.00   2026-01-30  0.01  6,350   5,195          1.22    100.0
INTC    60.00   2026-01-30  0.01  2,486   15,503         0.16    49.7
INTC    59.00   2026-01-30  0.01  2,409   1,783          1.35    48.2
NVDA    215.00  2026-01-30  0.01  2,193   11,050         0.20    43.9
INTC    69.00   2026-01-30  0.01  1,553   1,558          1.00    31.1
TSLA    700.00  2026-01-30  0.01  1,035   1,701          0.61    20.7
AAPL    325.00  2026-01-30  0.01  950     1,137          0.84    19.0
NIO     5.50    2026-01-30  0.01  945     12,489         0.08    18.9
```

## What to Look For

- **Clustered tickers**: Three of the top five are INTC calls at different strikes.
  This suggests concentrated betting on an Intel move before Friday expiration.
- **High volume with high Vol/OI**: INTC $59 has 2,409 volume against 1,783 OI
  (ratio 1.35). These are mostly new positions, not rollovers.
- **High volume with low Vol/OI**: INTC $60 has 2,486 volume but 15,503 OI
  (ratio 0.16). Lots of activity, but against a huge existing position -- could
  be hedging or rolling.

## Follow-Up: Validate with Balanced Scoring

Switch back to the default balanced score to see if these high-volume contracts
also rank well on proximity and IV:

```bash
uv run optionctl scan --universe volume --min-volume 50
```

The INTC $58 call drops from 100.0 to 23.1 because it's 36% OTM -- lots of
people are buying it, but it needs a massive move. Contracts that score high on
*both* volume and balanced weights are the strongest signals.
