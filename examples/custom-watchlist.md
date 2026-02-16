# Focusing on Your Own Ticker List

`optionctl` now scans the full S&P 500 by design.  
If you still want a personal subset, run JSON output and filter downstream.

## Example Focus List

```bash
FOCUS='["SPY","QQQ","AAPL","MSFT","NVDA"]'
```

## Filter a Full Scan to Your Focus Names

```bash
uv run optionctl scan --output json \
  | jq --argjson focus "$FOCUS" '[.[] | select(.ticker as $t | $focus | index($t))]'
```

## Only Strong Signals in Your Focus List

```bash
uv run optionctl scan --output json \
  | jq --argjson focus "$FOCUS" '
      [.[] | select(
        (.ticker as $t | $focus | index($t)) and
        .volume_oi_ratio >= 2 and
        .volume >= 500
      )]
    '
```
