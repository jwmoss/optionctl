# 0DTE Daily Playbook (SPY, ET)

Goal: run the same process every day, with fixed timing and fixed rules.

## Fixed Daily Settings

- Underlying: `SPY`
- Strategy window: `09:45-11:30 ET`
- Delta band: `0.50-0.60`
- Risk per trade: `1-2%` of account
- Max trades/day: `2-3`
- No averaging down

## One-Time Setup

```bash
uv sync
export POLYGON_API_KEY="your-key"
```

Or with the helper script:

```bash
./examples/zero-dte-day-trading.sh bootstrap
```

## Command Templates (Use These Every Day)

Signal command:

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --max-price 3.00 \
  --min-volume 200 \
  --delta-min 0.50 \
  --delta-max 0.60
```

Plan command (run only after choosing a contract and entry price):

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

## Daily Schedule

### Night Before (18:00-20:00 ET)

1. Mark prior day high/low/close and major support/resistance.
2. Confirm tomorrow's account risk and max trades.
3. Confirm environment works:

```bash
uv run optionctl zero-dte signal --ticker SPY --source polygon
```

Expected output: `waiting` or `no_trade` is fine here. This is a system check.
If market is closed, the signal can reference the prior trading session date.

### Premarket (08:45-09:20 ET)

1. Check SPY premarket direction and overnight range.
2. Check VIX regime (higher VIX -> reduce size).
3. Do not enter trades yet.

### Opening Range (09:30-09:44 ET)

1. No trades in this window.
2. Run signal once at ~09:35 and once at ~09:44:

```bash
uv run optionctl zero-dte signal --ticker SPY --source polygon
```

Expected output: `SPY ORB signal: waiting`.

### Entry Window (09:45-10:30 ET)

1. Run the signal command every 2 minutes.
2. Follow this rule table exactly:

| Output | What it means | What to do |
|------|---------|---------|
| `Session date (ET): YYYY-MM-DD` | Bars used for the signal | Confirm you are looking at today's session during market hours |
| `SPY ORB signal: waiting` | Opening range not complete | No trade, wait 2 min |
| `SPY ORB signal: no_trade` + `No ORB breakout beyond opening range.` | Price inside range | No trade, wait 2 min |
| `SPY ORB signal: no_trade` + `RSI(14) did not confirm.` | Breakout without confirmation | Skip setup, wait next signal |
| `SPY ORB signal: bullish` + contracts shown | Confirmed upside break | Pick top call candidate |
| `SPY ORB signal: bearish` + contracts shown | Confirmed downside break | Pick top put candidate |

3. If `bullish`/`bearish` appears and contracts are listed:
   - choose your contract
   - run `zero-dte plan` with your expected `--entry-price`
   - place trade once

### In-Between Management (After Entry)

1. Do not search for new setups while in a live trade.
2. Manage only the active position using plan outputs:
   - `Stop: $X.XX` -> exit at or below stop
   - `Target: $X.XX` -> take profit
   - `Time stop (ET): 11:30` -> force close regardless of P/L
3. If flat after exit and still below max trades, return to the 2-minute signal cycle.

### Late Morning (10:30-11:30 ET)

1. If still flat, reduce signal checks to every 5 minutes.
2. If no confirmed breakout by 11:30, no trade for the day.

### Hard Stop (11:30 ET)

1. Close any open 0DTE position at `11:30 ET`.
2. Stop taking new entries for the day.

### Post-Close (16:05-16:20 ET)

1. Log:
   - number of trades taken
   - whether rules were followed
   - exit reason (target, stop, or time stop)
2. Update notes for next night's prep.
