# SPY 0DTE Momentum Scalping

## Scenario

You want to find SPY options expiring today that are near the money with high
volume. These aren't penny options -- they cost more but have much higher delta
and gamma, meaning they move fast when SPY moves.

## Command

```bash
uv run optionctl spy momentum
```

With custom thresholds:

```bash
# Tighter range -- only contracts within 1% of current price
uv run optionctl spy momentum --max-distance 1.0

# Wider range, lower volume bar
uv run optionctl spy momentum --max-distance 3.0 --min-volume 200

# Prioritize proximity over everything else
uv run optionctl spy momentum --w-proximity 60 --w-volume 20 --w-vol-oi 10 --w-iv 10
```

## What to Look For

- **Proximity < 1%**: These contracts have the highest gamma. A $1 move in SPY
  can cause a $0.30-0.50 swing in the option premium.
- **High volume**: You need liquidity to get in and out quickly. Look for 1,000+
  volume on the strikes closest to the money.
- **Tight bid-ask spread**: Not shown in the scanner output, but check your
  broker before entering. Wide spreads eat into scalping profits.

## Trading Windows

- **9:30-10:30 AM ET**: Opening volatility. SPY often moves $1+ in the first
  hour as overnight orders clear and news gets priced in.
- **3:30-4:00 PM ET**: Closing moves. Institutional rebalancing and gamma
  hedging can cause sharp directional moves in the last 30 minutes.
- **Avoid 11:00 AM - 2:00 PM ET**: Midday is typically low volatility.
  Theta decay is eating your premium while price chops sideways.

## Risk Management

- Set a hard stop-loss at 50% of entry. If you buy at $0.50, exit at $0.25.
- Take profits at 20-30% gain. Don't hold for a home run -- 0DTE theta is
  relentless.
- Size positions small. Even near-the-money 0DTE contracts can go to zero in
  minutes if SPY moves against you.
