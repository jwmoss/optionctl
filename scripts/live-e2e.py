"""Read actual SPY option data through the installed CLI."""

# This executable is not a package; subprocess arguments are fixed below.
# ruff: noqa: INP001, S603

import json
import subprocess
import sys


def main() -> None:
    """Require a live contract and a valid empty JSON scan."""
    command = [
        "optionctl",
        "scan",
        "--ticker",
        "SPY",
        "--min-volume",
        "0",
        "--min-vol-oi",
        "0",
        "--max-price",
        "100",
        "--limit",
        "1",
        "--output",
        "json",
    ]
    result = subprocess.run(
        [*command, "--refresh"], capture_output=True, text=True, timeout=120, check=True
    )
    rows = json.loads(result.stdout)
    if not rows or not rows[0].get("contract_symbol") or rows[0].get("ticker") != "SPY":
        msg = "No real SPY contract returned; inspect market-data availability"
        raise RuntimeError(msg)
    result = subprocess.run(
        [*command, "--max-price", "0"], capture_output=True, text=True, timeout=120, check=True
    )
    if json.loads(result.stdout) != []:
        msg = "Empty scan did not return an empty JSON array"
        raise RuntimeError(msg)
    print("PASS real market-data CLI reads")  # noqa: T201


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL {error}", file=sys.stderr)  # noqa: T201
        sys.exit(1)
