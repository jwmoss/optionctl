# 0DTE ORB Penny Scenarios (`$0.01` Contracts)

These are execution examples for aggressive penny-contract ORB trades.

Use this profile only if you intentionally want high-risk, farther-OTM behavior.

## Command Profile

Use the helper:

```bash
./examples/zero-dte-day-trading.sh signal-penny
```

Equivalent direct command:

```bash
uv run optionctl zero-dte signal \
  --ticker SPY \
  --source polygon \
  --max-price 0.01 \
  --min-volume 200 \
  --delta-min 0.01 \
  --delta-max 0.20
```

## Penny Timeline (ET): What To Run And Expect

| Time | What to run | What to expect | What to do |
|------|-------------|----------------|------------|
| 09:30-09:44 | `opening-check` | `waiting` or `no_trade` | Buy nothing |
| 09:45-10:20 | `signal-penny` every 2 min | First valid breakout attempts | Trade only confirmed `bullish`/`bearish` |
| 10:20-10:45 | `signal-penny` every 3-5 min | More fakeouts, lower quality | Trade only if fill is still near `0.01` |
| 10:45-11:30 | no new entries | Theta decay accelerates | Manage open trades only |
| 11:30 | n/a | Time-stop point | Close all open positions |

## What To Buy (Exact Rules)

When you get `SPY ORB signal: bullish`:

1. Buy the first `C` row in the table that still has `Ask 0.01`.
2. Require `Delta` in `0.01-0.20`.
3. Prefer higher `Vol` when multiple rows qualify.

When you get `SPY ORB signal: bearish`:

1. Buy the first `P` row in the table that still has `Ask 0.01`.
2. Require absolute `Delta` in `0.01-0.20`.
3. Prefer higher `Vol` when multiple rows qualify.

Skip the setup if:

1. top row no longer fills near `0.01`
2. all rows are illiquid
3. signal happens after `10:45 ET`

## Entry And Fill Protocol

1. Enter within 1 minute of the valid signal.
2. Place limit at `0.01`.
3. If not filled quickly, allow one reprice to `0.02`.
4. If still not filled, cancel and skip (do not chase).

## Core Rule For Contract Selection

When output is `bullish` or `bearish`, use the first row in the contract table
by default.

For penny mode, skip entries when spread/liquidity is poor:

1. avoid rows with very low volume
2. avoid rows where ask is `0.01` but fills only happen at much higher prices

## Core Rule For Entry Timing

- Valid entries: `09:45-10:20 ET`
- Cautious entries: `10:20-10:45 ET`
- No new entries after: `10:45 ET`
- Force close by: `11:30 ET`

## Risk Model For `$0.01` Contracts

Penny contracts behave close to binary outcomes (quick double or near-zero).

Suggested plan call:

```bash
./examples/zero-dte-day-trading.sh plan 0.01
```

Practical interpretation:

1. target first scale at `0.02` (100%)
2. if no follow-through, exit fast on momentum failure
3. treat risk as potentially full premium loss

What to expect:

1. many trades will fail quickly
2. a smaller number can move very fast
3. late entries usually perform worse due to decay

## Scenario 1: Clean Bullish Breakout, Cheap Calls Available

Signal output (example):

```text
SPY ORB signal: bullish
Session date (ET): 2026-02-18
Breakout: 2026-02-18T09:49:00-05:00 @ 687.20
Reason: ORB + RSI confirmed.
```

Table row (example):

```text
Ticker  C/P  Strike   Ask   Delta  Vol
SPY      C   689.00  0.01   0.12   4200
```

Action:

1. At `09:49-09:50 ET`, place `0.01` limit on first call row (`689C` in this example).
2. If no fill, allow one reprice to `0.02`, then stop.
3. First take-profit at `0.02`.
4. Keep runner only if SPY trend remains strong.

## Scenario 2: Clean Bearish Breakout, Cheap Puts Available

Output (example):

```text
SPY ORB signal: bearish
Reason: ORB + RSI confirmed.
```

Action:

1. At signal time, buy first put row near `0.01`.
2. Use same fill rule: `0.01` then single reprice to `0.02` max.
3. Take first profit at `0.02`.
4. Exit remaining size if price snaps back into opening range.

## Scenario 3: `bullish`/`bearish` But Fill Is Not Actually `0.01`

Example condition:

- table shows `Ask 0.01`
- live fills are `0.03` or higher

Action:

1. Do not chase blindly.
2. Re-run signal once.
3. If still no realistic `0.01` fills, skip setup.

## Scenario 4: `no_trade` Because RSI Did Not Confirm

Output:

```text
SPY ORB signal: no_trade
Reason: Breakout occurred but RSI(14) did not confirm.
```

Action:

1. No entry.
2. Wait for the next scheduled check.

## Scenario 5: `bullish` But No Matching Penny Contracts

Output:

```text
SPY ORB signal: bullish
No matching 0DTE contracts for the signal filters.
```

Action:

1. First, lower `--min-volume` (example `200 -> 100`) and retry.
2. If still empty, skip penny mode for that setup.
3. Optional fallback: use standard ORB profile (`signal` instead of `signal-penny`).

## Scenario 6: Entry Taken, Contract Doubles Fast

Example:

- Enter at `0.01`
- prints `0.02` within minutes

Action:

1. Take at least partial profit immediately.
2. If keeping a runner, lock in gains and keep hard time stop at `11:30 ET`.

## Scenario 7: Entry Stalls Near `0.01`

Example:

- price does not lift off within a few bars after entry

Action:

1. Cut early on failed momentum.
2. Do not sit through theta decay hoping for late move.

## Scenario 8: Position Still Open Near 11:30

Action:

1. Exit at or before `11:30 ET`.
2. Do not carry 0DTE penny lotto exposure past your cutoff.

## Quick Decision Tree

1. `waiting` -> no trade.
2. `no_trade` -> no trade.
3. `bullish`/`bearish` + liquid `0.01` row before `10:45 ET` -> enter quickly, target `0.02`.
4. No realistic `0.01` fill -> skip.
5. Close all open positions by `11:30 ET`.
