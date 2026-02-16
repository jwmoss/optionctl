#!/usr/bin/env bash
set -euo pipefail

# Optional when using Polygon data source:
# export POLYGON_API_KEY="your-key"

echo "1) ORB + RSI signal and 0DTE ideas"
uv run optionctl zero-dte signal --ticker SPY --source polygon --max-price 3.00 --min-volume 200 --delta-min 0.50 --delta-max 0.60

echo
echo "2) Position plan"
uv run optionctl zero-dte plan --account-size 25000 --entry-price 1.50 --risk-pct 1.2 --stop-loss-pct 40 --target-pct 100 --time-stop 11:30 --max-trades 3

echo
echo "3) JSON output example"
uv run optionctl zero-dte signal --ticker SPY --source polygon --output json

echo
echo "4) Optional: disable RSI confirmation"
uv run optionctl zero-dte signal --ticker SPY --source polygon --no-rsi-confirmation
