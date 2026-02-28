"""Tests for predictions database and Brier score calibration."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from optionctl.models import OptionCandidate
from optionctl.predictions import (
    Prediction,
    _db,
    _init_db,
    compute_brier_score,
    get_calibration_summary,
    record_predictions,
    resolve_outcomes,
)

_TODAY = datetime.now(tz=UTC).date()
_NOW = datetime.now(tz=UTC)
_YESTERDAY = _TODAY - timedelta(days=1)


@pytest.fixture
def pred_db(tmp_path):
    """Set up a temporary predictions database."""
    db_path = tmp_path / "predictions.db"
    _init_db(db_path)
    yield db_path
    _db.close()


def _make_candidate(
    contract_symbol: str = "AAPL260320C00150000",
    ticker: str = "AAPL",
    strike: float = 150.0,
    p_itm: float = 0.3,
    underlying_price: float = 145.0,
) -> OptionCandidate:
    """Build an OptionCandidate with sensible defaults."""
    return OptionCandidate(
        ticker=ticker,
        strike=strike,
        expiration=date(2026, 3, 20),
        bid=0.01,
        ask=0.01,
        last_price=0.01,
        volume=500,
        open_interest=100,
        implied_volatility=0.5,
        underlying_price=underlying_price,
        dte=5,
        p_itm=p_itm,
        contract_symbol=contract_symbol,
    )


class TestRecordPredictions:
    """Tests for record_predictions()."""

    def test_saves_candidates(self, pred_db):
        """Two distinct candidates should persist as two rows."""
        candidates = [
            _make_candidate(contract_symbol="AAPL260320C00150000", p_itm=0.3),
            _make_candidate(contract_symbol="AAPL260320C00155000", p_itm=0.1, strike=155.0),
        ]
        count = record_predictions(candidates, db_path=pred_db)
        assert count == 2
        assert Prediction.select().count() == 2

    def test_upsert_same_contract_same_day(self, pred_db):
        """Re-scanning the same contract should update, not duplicate."""
        record_predictions([_make_candidate(p_itm=0.3)], db_path=pred_db)
        record_predictions([_make_candidate(p_itm=0.5)], db_path=pred_db)
        assert Prediction.select().count() == 1
        assert abs(Prediction.get().p_itm - 0.5) < 0.001

    def test_empty_list(self, pred_db):
        """Empty candidate list should return 0."""
        assert record_predictions([], db_path=pred_db) == 0

    def test_skips_no_contract_symbol(self, pred_db):
        """Candidates without a contract symbol should be skipped."""
        assert record_predictions([_make_candidate(contract_symbol="")], db_path=pred_db) == 0


class TestComputeBrierScore:
    """Tests for compute_brier_score()."""

    def test_known_brier(self, pred_db):
        """p_itm=0.8, outcome=True → (0.8 - 1.0)^2 = 0.04."""
        Prediction.create(
            contract_symbol="TEST1",
            ticker="AAPL",
            strike=150.0,
            expiration=_YESTERDAY,
            scan_date=_TODAY,
            underlying_price_at_scan=145.0,
            p_itm=0.8,
            outcome=True,
            resolved_at=_NOW,
        )
        score = compute_brier_score(days=30, db_path=pred_db)
        assert score is not None
        assert abs(score - 0.04) < 0.0001

    def test_no_data_returns_none(self, pred_db):
        """No resolved data should return None."""
        assert compute_brier_score(days=30, db_path=pred_db) is None

    def test_multiple_predictions(self, pred_db):
        """Two predictions: (0.8-1)^2=0.04 and (0.2-0)^2=0.04 → mean=0.04."""
        Prediction.create(
            contract_symbol="A",
            ticker="A",
            strike=100,
            expiration=_YESTERDAY,
            scan_date=_TODAY,
            underlying_price_at_scan=95,
            p_itm=0.8,
            outcome=True,
            resolved_at=_NOW,
        )
        Prediction.create(
            contract_symbol="B",
            ticker="B",
            strike=100,
            expiration=_YESTERDAY,
            scan_date=_TODAY,
            underlying_price_at_scan=95,
            p_itm=0.2,
            outcome=False,
            resolved_at=_NOW,
        )
        score = compute_brier_score(days=30, db_path=pred_db)
        assert score is not None
        assert abs(score - 0.04) < 0.0001


class TestGetCalibrationSummary:
    """Tests for get_calibration_summary()."""

    def test_returns_correct_keys(self, pred_db):
        """Summary dict must contain the expected keys."""
        summary = get_calibration_summary(days=30, db_path=pred_db)
        assert set(summary.keys()) == {
            "brier_score",
            "n_predictions",
            "n_resolved",
            "mean_p_itm",
            "hit_rate",
        }

    def test_with_data(self, pred_db):
        """Resolved hit should yield hit_rate=1.0."""
        Prediction.create(
            contract_symbol="X",
            ticker="X",
            strike=50,
            expiration=_YESTERDAY,
            scan_date=_TODAY,
            underlying_price_at_scan=48,
            p_itm=0.6,
            outcome=True,
            resolved_at=_NOW,
        )
        summary = get_calibration_summary(days=30, db_path=pred_db)
        assert summary["n_predictions"] == 1
        assert summary["n_resolved"] == 1
        assert summary["hit_rate"] == 1.0


class TestResolveOutcomes:
    """Tests for resolve_outcomes()."""

    @patch("optionctl.predictions.yf.Ticker")
    def test_no_unresolved(self, mock_ticker_cls, pred_db):
        """No unresolved predictions → no yfinance calls."""
        count = resolve_outcomes(db_path=pred_db)
        assert count == 0
        mock_ticker_cls.assert_not_called()

    @patch("optionctl.predictions.yf.Ticker")
    def test_resolves_expired(self, mock_ticker_cls, pred_db):
        """Expired unresolved prediction should be resolved with yfinance price."""
        mock_ticker = MagicMock()
        mock_ticker.fast_info.last_price = 160.0
        mock_ticker_cls.return_value = mock_ticker

        Prediction.create(
            contract_symbol="R1",
            ticker="AAPL",
            strike=150.0,
            expiration=_YESTERDAY,
            scan_date=_TODAY - timedelta(days=5),
            underlying_price_at_scan=145.0,
            p_itm=0.6,
        )
        count = resolve_outcomes(db_path=pred_db)
        assert count == 1
        pred = Prediction.get()
        assert pred.outcome is True  # 160 > 150
        assert pred.resolved_at is not None
