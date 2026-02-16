# 0DTE ORB Workflow

This example follows the research playbook:

1. Wait for the 9:30-9:45 ET opening range.
2. Trade only a breakout with RSI confirmation.
3. Choose slightly ITM contracts around 0.50-0.60 delta.
4. Size risk at 1-2% of account, with fixed stop/target and time stop.

## Prerequisites

```bash
uv sync
export POLYGON_API_KEY="your-key"
```

## Real-Time Runbook (ET)

### 9:20-9:29 (Prep)

1. Mark prior day high/low/close and key support/resistance.
2. Check pre-market SPY direction and VIX regime.
3. Decide account risk and max trades for the day (usually 1-2% risk, 2-3 trades max).

### 9:30-9:44 (No trade window)

Run signal only for awareness. You should see `waiting` and do nothing.

```bash
uv run optionctl zero-dte signal --ticker SPY --source polygon
```

### 9:45-11:30 (Execution window)

Run the signal command every 1-2 minutes until you get a valid setup:

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --max-price 3.00 \
  --min-volume 200 \
  --delta-min 0.50 \
  --delta-max 0.60
```

Use the command output to decide:

| Output | Meaning | Action |
|------|---------|---------|
| `SPY ORB signal: waiting` | 9:30-9:44 range still forming | No trade |
| `SPY ORB signal: no_trade` + `No ORB breakout beyond opening range.` | Price is chopping inside range | No trade, keep waiting |
| `SPY ORB signal: no_trade` + `RSI(14) did not confirm.` | Breakout happened without RSI cross | Skip trade |
| `SPY ORB signal: bullish` + contract table | Break above 15-min high with confirmation | Consider top 0DTE call idea |
| `SPY ORB signal: bearish` + contract table | Break below 15-min low with confirmation | Consider top 0DTE put idea |

If `bullish`/`bearish` prints but no contracts are returned, relax filters (for example increase `--max-price` or lower `--min-volume`) and rerun.

## 1. Generate Signal + Contract Ideas

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --max-price 3.00 \
  --min-volume 200 \
  --delta-min 0.50 \
  --delta-max 0.60
```

Notes:

- `polygon` is recommended for Greeks (`delta`, `gamma`, `theta`, `vega`).
- The command prints ORB direction (`bullish`, `bearish`, `no_trade`, `waiting`)
  and then returns matching same-day contracts.

## 2. Build Position Plan

After you choose a contract and know your expected fill price, generate a plan:

```bash
uv run optionctl zero-dte plan \
  --account-size 25000 \
  --entry-price 1.50 \
  --risk-pct 1.2 \
  --stop-loss-pct 40 \
  --target-pct 100 \
  --time-stop 11:30 \
  --max-trades 3
```

Use plan output as hard exits:

- `Stop: $X.XX` -> exit when contract trades at or below this level.
- `Target: $X.XX` -> take profits at this level (or scale out).
- `Time stop (ET): 11:30` -> close the trade at this time even if flat.
- `Max trades/day: N` -> stop trading after N entries.

This aligns with the research guardrails:

- Profit target typically 50-100% (`--target-pct 50` to `100`)
- Stop loss typically 30-50% (`--stop-loss-pct 30` to `50`)
- No averaging down

## 3. JSON Output for Automation

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --output json
```

Tip: parse `signal`, `reason`, and returned contracts to automate "trade vs no-trade" routing.

## 4. Allow Breakouts Without RSI Cross (Optional)

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --no-rsi-confirmation
```
