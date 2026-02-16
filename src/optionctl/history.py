"""Daily volume history for computing rolling average baselines."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate

logger = logging.getLogger(__name__)

_HISTORY_DIR = Path.home() / ".cache" / "optionctl" / "history"


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now(tz=UTC).date().isoformat()


def record_volume_snapshot(candidates: list[OptionCandidate]) -> None:
    """Save daily volume per contract symbol to a date-stamped file.

    Args:
        candidates: List of scanned option candidates.
    """
    if not candidates:
        return

    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path = _HISTORY_DIR / f"{_today_str()}.json"

        existing: dict[str, int] = {}
        if path.exists():
            existing = json.loads(path.read_text())

        for c in candidates:
            if c.contract_symbol:
                existing[c.contract_symbol] = c.volume

        path.write_text(json.dumps(existing))
    except OSError:
        logger.debug("Failed to write volume history snapshot")


def get_volume_history(contract_symbol: str, days: int = 5) -> list[int]:
    """Load volume values for a contract from the last N date files.

    Args:
        contract_symbol: Option contract symbol.
        days: Number of past days to look back.

    Returns:
        List of historical volume values found.
    """
    today = datetime.now(tz=UTC).date()
    volumes: list[int] = []

    for offset in range(1, days + 1):
        history_date = today - timedelta(days=offset)
        path = _HISTORY_DIR / f"{history_date.isoformat()}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            if contract_symbol in data:
                volumes.append(data[contract_symbol])
        except (json.JSONDecodeError, OSError):
            continue

    return volumes


def get_avg_volume(contract_symbol: str, days: int = 5) -> float | None:
    """Compute rolling average volume for a contract.

    Args:
        contract_symbol: Option contract symbol.
        days: Number of past days to average.

    Returns:
        Average volume, or None if fewer than 2 data points.
    """
    history = get_volume_history(contract_symbol, days)
    if len(history) < 2:  # noqa: PLR2004
        return None
    return sum(history) / len(history)


def compute_vol_vs_avg(current_volume: int, contract_symbol: str, days: int = 5) -> float | None:
    """Compute the ratio of current volume to rolling average.

    Args:
        current_volume: Today's volume for the contract.
        contract_symbol: Option contract symbol.
        days: Number of past days to average.

    Returns:
        Multiplier (e.g. 3.5 = 3.5x average), or None if no baseline.
    """
    avg = get_avg_volume(contract_symbol, days)
    if avg is None or avg <= 0:
        return None
    return current_volume / avg


def cleanup_old_history(max_age_days: int = 30) -> int:
    """Remove history files older than max_age_days.

    Args:
        max_age_days: Delete files older than this many days.

    Returns:
        Number of files removed.
    """
    if not _HISTORY_DIR.exists():
        return 0

    cutoff = datetime.now(tz=UTC).date() - timedelta(days=max_age_days)
    removed = 0

    for path in _HISTORY_DIR.glob("*.json"):
        try:
            file_date_str = path.stem
            file_date = datetime.fromisoformat(file_date_str).date()
            if file_date < cutoff:
                path.unlink()
                removed += 1
        except (ValueError, OSError):
            continue

    return removed
