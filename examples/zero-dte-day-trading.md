# 0DTE ORB Workflow

This example follows the research playbook:

1. Wait for the 9:30-9:45 ET opening range.
2. Trade only a breakout with RSI confirmation.
3. Choose slightly ITM contracts around 0.50-0.60 delta.
4. Size risk at 1-2% of account, with fixed stop/target and time stop.

## 1. Generate Signal + Contract Ideas

```bash
make run ARGS="zero-dte signal --ticker SPY --source polygon --max-price 3.00 --min-volume 200 --delta-min 0.50 --delta-max 0.60"
```

Notes:

- `polygon` is recommended for Greeks (`delta`, `gamma`, `theta`, `vega`).
- The command prints ORB direction (`bullish`, `bearish`, `no_trade`, `waiting`)
  and then returns matching same-day contracts.

## 2. Build Position Plan

```bash
make run ARGS="zero-dte plan --account-size 25000 --entry-price 1.50 --risk-pct 1.2 --stop-loss-pct 40 --target-pct 100 --time-stop 11:30 --max-trades 3"
```

## 3. JSON Output for Automation

```bash
make run ARGS="zero-dte signal --ticker SPY --source polygon --output json"
```

## 4. Allow Breakouts Without RSI Cross (Optional)

```bash
make run ARGS="zero-dte signal --ticker SPY --source polygon --no-rsi-confirmation"
```
