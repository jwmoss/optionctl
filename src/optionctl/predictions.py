"""Predictions database for Brier score calibration tracking."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import yfinance as yf
from peewee import (
    BooleanField,
    CharField,
    DateField,
    DateTimeField,
    FloatField,
    Model,
    SqliteDatabase,
)

if TYPE_CHECKING:
    from optionctl.models import OptionCandidate

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".optionctl" / "predictions.db"
_db = SqliteDatabase(None)

_BRIER_EXCELLENT = 0.10
_BRIER_GOOD = 0.20


def _init_db(path: Path | None = None) -> SqliteDatabase:
    """Initialize the predictions database."""
    db_path = path or _DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db.init(str(db_path))
    _db.connect(reuse_if_open=True)
    _db.create_tables([Prediction])
    return _db


class Prediction(Model):
    """A recorded p_itm prediction for calibration tracking."""

    contract_symbol = CharField()
    ticker = CharField()
    strike = FloatField()
    expiration = DateField()
    scan_date = DateField()
    underlying_price_at_scan = FloatField()
    p_itm = FloatField()
    outcome = BooleanField(null=True)
    resolved_at = DateTimeField(null=True)

    class Meta:  # noqa: D106
        """Peewee model metadata."""

        database = _db
        indexes = ((("contract_symbol", "scan_date"), True),)  # unique together


def record_predictions(candidates: list[OptionCandidate], *, db_path: Path | None = None) -> int:
    """Record p_itm predictions from scan candidates.

    Upserts by (contract_symbol, scan_date). Returns count saved.

    Args:
        candidates: List of scored option candidates from a scan.
        db_path: Optional override for DB path (used in tests).

    Returns:
        Number of predictions saved.
    """
    if not candidates:
        return 0

    _init_db(db_path)
    today = datetime.now(tz=UTC).date()
    count = 0

    with _db.atomic():
        for c in candidates:
            if not c.contract_symbol:
                continue
            Prediction.insert(
                contract_symbol=c.contract_symbol,
                ticker=c.ticker,
                strike=c.strike,
                expiration=c.expiration,
                scan_date=today,
                underlying_price_at_scan=c.underlying_price,
                p_itm=c.p_itm,
            ).on_conflict(
                conflict_target=[Prediction.contract_symbol, Prediction.scan_date],
                update={
                    Prediction.p_itm: c.p_itm,
                    Prediction.underlying_price_at_scan: c.underlying_price,
                },
            ).execute()
            count += 1

    return count


def resolve_outcomes(*, db_path: Path | None = None) -> int:
    """Resolve outcomes for expired, unresolved predictions.

    Fetches final underlying price via yfinance and sets outcome = (final_price > strike).

    Args:
        db_path: Optional override for DB path (used in tests).

    Returns:
        Number of predictions resolved.
    """
    _init_db(db_path)
    today = datetime.now(tz=UTC).date()

    unresolved = Prediction.select().where(
        Prediction.outcome.is_null(),
        Prediction.expiration <= today,
    )

    # Group by ticker to minimize API calls
    ticker_predictions: dict[str, list[Prediction]] = {}
    for pred in unresolved:
        ticker_predictions.setdefault(pred.ticker, []).append(pred)

    count = 0
    now = datetime.now(tz=UTC)

    for ticker, preds in ticker_predictions.items():
        try:  # noqa: SIM105
            stock = yf.Ticker(ticker)
            price = float(stock.fast_info.last_price)
        except (ValueError, TypeError, KeyError):
            logger.warning("Failed to fetch price for %s during resolution", ticker)
            continue

        with _db.atomic():
            for pred in preds:
                pred.outcome = price > pred.strike
                pred.resolved_at = now
                pred.save()
                count += 1

    return count


def compute_brier_score(days: int = 30, *, db_path: Path | None = None) -> float | None:
    """Compute Brier score over resolved predictions in last N days.

    Brier = mean((p_itm - outcome)^2). Lower is better.
    Returns None if no resolved data.

    Args:
        days: Lookback window in days.
        db_path: Optional override for DB path (used in tests).

    Returns:
        Brier score, or None if no resolved predictions.
    """
    _init_db(db_path)
    cutoff = datetime.now(tz=UTC).date() - timedelta(days=days)

    resolved = Prediction.select().where(
        Prediction.outcome.is_null(False),  # noqa: FBT003
        Prediction.scan_date >= cutoff,
    )

    scores = []
    for pred in resolved:
        outcome_val = 1.0 if pred.outcome else 0.0
        scores.append((pred.p_itm - outcome_val) ** 2)

    if not scores:
        return None

    return sum(scores) / len(scores)


def get_calibration_summary(days: int = 30, *, db_path: Path | None = None) -> dict:
    """Get calibration summary stats over last N days.

    Returns dict with: brier_score, n_predictions, n_resolved, mean_p_itm, hit_rate.

    Args:
        days: Lookback window in days.
        db_path: Optional override for DB path (used in tests).

    Returns:
        Dict with brier_score, n_predictions, n_resolved, mean_p_itm, hit_rate.
    """
    _init_db(db_path)
    cutoff = datetime.now(tz=UTC).date() - timedelta(days=days)

    all_preds = list(Prediction.select().where(Prediction.scan_date >= cutoff))
    resolved = [p for p in all_preds if p.outcome is not None]

    n_predictions = len(all_preds)
    n_resolved = len(resolved)
    brier = compute_brier_score(days, db_path=db_path)

    if resolved:
        mean_p_itm = sum(p.p_itm for p in resolved) / n_resolved
        hit_rate = sum(1 for p in resolved if p.outcome) / n_resolved
    else:
        mean_p_itm = 0.0
        hit_rate = 0.0

    return {
        "brier_score": brier,
        "n_predictions": n_predictions,
        "n_resolved": n_resolved,
        "mean_p_itm": round(mean_p_itm, 4),
        "hit_rate": round(hit_rate, 4),
    }
