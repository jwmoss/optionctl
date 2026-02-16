# 0DTE ORB Scenarios (What To Do When X Happens)

These are execution examples for the ORB playbook using `optionctl` output.

## Core Rule For Contract Selection

When `zero-dte signal` returns `bullish` or `bearish`, use the first row in the
contract table by default.

Why: contracts are already ranked by:

1. delta closeness to target band midpoint (default `0.55`)
2. higher volume
3. closer strike proximity

## Core Rule For Entry Timing

- Valid entries: `09:45-10:30 ET`
- Cautious entries: `10:30-11:00 ET`
- No new entries after: `11:00 ET`
- Force close all open positions by: `11:30 ET`

## Scenario 1: Clean Bullish Breakout At 09:47

Signal output (example):

```text
SPY ORB signal: bullish
Session date (ET): 2026-02-17
Breakout: 2026-02-17T09:47:00-05:00 @ 684.10
Reason: ORB + RSI confirmed.
```

Top table row (example):

```text
Ticker  C/P  Strike   Ask   Delta  Vol
SPY      C   684.00  1.45   0.55   1800
```

Action:

1. Buy that first call row (`684C`) near shown ask (`~1.45`).
2. Run:

```bash
./examples/zero-dte-day-trading.sh plan 1.45
```

3. Use plan outputs:
   - stop around `0.87` (40% stop)
   - target around `2.90` (100% target)
   - time stop `11:30 ET`

## Scenario 2: Clean Bearish Breakout At 10:02

Signal output (example):

```text
SPY ORB signal: bearish
Session date (ET): 2026-02-17
Breakout: 2026-02-17T10:02:00-05:00 @ 679.80
Reason: ORB + RSI confirmed.
```

Action:

1. Buy first put row in returned table.
2. Run plan using that row's ask as `entry_price`.
3. Use the same stop/target/time-stop process.

## Scenario 3: `no_trade` Because RSI Did Not Confirm

Output (example):

```text
SPY ORB signal: no_trade
Reason: Breakout occurred but RSI(14) did not confirm.
```

Action:

1. Do not enter.
2. Wait for next 2-minute check.
3. Do not front-run a second breakout before a fresh signal.

## Scenario 4: `no_trade` Because Price Is Still In Range

Output (example):

```text
SPY ORB signal: no_trade
Reason: No ORB breakout beyond opening range.
```

Action:

1. Do not enter.
2. Keep scanning on schedule.
3. If still no breakout by `11:30 ET`, no trade day.

## Scenario 5: `bullish` But No Contracts Listed

Output (example):

```text
SPY ORB signal: bullish
No matching 0DTE contracts for the signal filters.
```

Action:

1. First retry by loosening one filter only:
   - increase `--max-price` (for example `3.00 -> 5.00`) or
   - reduce `--min-volume` (for example `200 -> 100`)
2. Re-run immediately.
3. If still empty, skip the setup.

## Scenario 6: Entry Taken, Target Hits Quickly

Example:

- Enter `1.20`
- Plan target (100%) is `2.40`

Action:

1. Exit full at target, or scale out (for example 70-100%).
2. Record result.
3. Only take another signal if below daily max trades.

## Scenario 7: Entry Taken, Stop Hits

Example:

- Enter `1.20`
- Plan stop (40%) is `0.72`

Action:

1. Exit immediately at stop.
2. No averaging down.
3. Continue only if:
   - a brand-new confirmed signal appears, and
   - you still have remaining daily trade slots.

## Scenario 8: Position Drifts, No Follow-Through

Example:

- Position remains around entry, no target/stop hit.

Action:

1. Exit at `11:30 ET` time stop.
2. Do not hold 0DTE past the playbook cutoff.

## Quick Decision Tree

1. `waiting` -> no trade.
2. `no_trade` (range or RSI fail) -> no trade.
3. `bullish` or `bearish` + table rows -> trade first row within time window.
4. Use `plan` output for stop/target/time-stop.
5. Stop for day at max trades or after `11:30 ET`.
