#!/usr/bin/env bash
set -euo pipefail

TICKER="${TICKER:-SPY}"
SOURCE="${SOURCE:-polygon}"
MAX_PRICE="${MAX_PRICE:-3.00}"
MIN_VOLUME="${MIN_VOLUME:-200}"
DELTA_MIN="${DELTA_MIN:-0.50}"
DELTA_MAX="${DELTA_MAX:-0.60}"

ACCOUNT_SIZE="${ACCOUNT_SIZE:-25000}"
RISK_PCT="${RISK_PCT:-1.2}"
STOP_LOSS_PCT="${STOP_LOSS_PCT:-40}"
TARGET_PCT="${TARGET_PCT:-100}"
TIME_STOP="${TIME_STOP:-11:30}"
MAX_TRADES="${MAX_TRADES:-3}"

usage() {
  cat <<'EOF'
Usage:
  ./examples/zero-dte-day-trading.sh bootstrap
  ./examples/zero-dte-day-trading.sh night-before
  ./examples/zero-dte-day-trading.sh opening-check
  ./examples/zero-dte-day-trading.sh signal
  ./examples/zero-dte-day-trading.sh signal-json
  ./examples/zero-dte-day-trading.sh plan <entry_price>

Schedule (ET):
  - First run only: `bootstrap`
  - Night before: run `night-before`
  - 09:30-09:44: run `opening-check` only (no trades)
  - 09:45-10:30: run `signal` every 2 minutes
  - 10:30-11:30: run `signal` every 5 minutes
  - Hard close open trade by 11:30 using plan time stop

Optional env vars:
  TICKER, SOURCE, MAX_PRICE, MIN_VOLUME, DELTA_MIN, DELTA_MAX
  ACCOUNT_SIZE, RISK_PCT, STOP_LOSS_PCT, TARGET_PCT, TIME_STOP, MAX_TRADES
EOF
}

signal_cmd() {
  uv run optionctl zero-dte signal \
    --ticker "$TICKER" \
    --source "$SOURCE" \
    --max-price "$MAX_PRICE" \
    --min-volume "$MIN_VOLUME" \
    --delta-min "$DELTA_MIN" \
    --delta-max "$DELTA_MAX" \
    "$@"
}

phase="${1:-}"
case "$phase" in
  bootstrap)
    uv sync
    ;;
  night-before)
    echo "Night-before system check (connectivity + API only)."
    tmp_output="$(mktemp)"
    if uv run optionctl zero-dte signal --ticker "$TICKER" --source "$SOURCE" >"$tmp_output" 2>&1; then
      signal_line="$(grep -m1 "ORB signal:" "$tmp_output" || true)"
      session_line="$(grep -m1 "Session date (ET):" "$tmp_output" || true)"
      reason_line="$(grep -m1 "^Reason:" "$tmp_output" || true)"
      today_et="$(TZ=America/New_York date +%F)"

      echo "System check: OK"
      [[ -n "$signal_line" ]] && echo "$signal_line"
      [[ -n "$session_line" ]] && echo "$session_line"
      [[ -n "$reason_line" ]] && echo "$reason_line"

      if [[ -n "$session_line" && "$session_line" != *"$today_et"* ]]; then
        echo "Info: session date is before today ($today_et). Normal outside market hours."
      fi
    else
      cat "$tmp_output" >&2
      rm -f "$tmp_output"
      exit 1
    fi
    rm -f "$tmp_output"
    ;;
  opening-check)
    uv run optionctl zero-dte signal --ticker "$TICKER" --source "$SOURCE"
    ;;
  signal)
    signal_cmd
    ;;
  signal-json)
    signal_cmd --output json
    ;;
  plan)
    entry_price="${2:-}"
    if [[ -z "$entry_price" ]]; then
      echo "Missing entry price. Example: ./examples/zero-dte-day-trading.sh plan 1.50" >&2
      exit 1
    fi
    uv run optionctl zero-dte plan \
      --account-size "$ACCOUNT_SIZE" \
      --entry-price "$entry_price" \
      --risk-pct "$RISK_PCT" \
      --stop-loss-pct "$STOP_LOSS_PCT" \
      --target-pct "$TARGET_PCT" \
      --time-stop "$TIME_STOP" \
      --max-trades "$MAX_TRADES"
    ;;
  *)
    usage
    exit 1
    ;;
esac
