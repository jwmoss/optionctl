"""Tests for predictions database and Brier score calibration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
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


@pytest.fixture()
def pred_db(tmp_path):
    """Set up a temporary predictions database."""
    db_path = tmp_path / "predictions.db"
    _init_db(db_path)
    yield db_path
    _db.close()


def _make_candidate(**kwargs) -> OptionCandidate:
    defaults = dict(
        ticker="AAPL",
        strike=150.0,
        expiration=date(2026, 3, 20),
        bid=0.01,
        ask=0.01,
        last_price=0.01,
        volume=500,
        open_interest=100,
        implied_volatility=0.5,
        underlying_price=145.0,
        dte=5,
        p_itm=0.3,
        contract_symbol="AAPL260320C00150000",
    )
    defaults.update(kwargs)
    return OptionCandidate(**defaults)


class TestRecordPredictions:
    def test_saves_candidates(self, pred_db):
        candidates = [
            _make_candidate(contract_symbol="AAPL260320C00150000", p_itm=0.3),
            _make_candidate(contract_symbol="AAPL260320C00155000", p_itm=0.1, strike=155.0),
        ]
        count = record_predictions(candidates, db_path=pred_db)
        assert count == 2
        assert Prediction.select().count() == 2

    def test_upsert_same_contract_same_day(self, pred_db):
        c = _make_candidate(p_itm=0.3)
        record_predictions([c], db_path=pred_db)
        c2 = _make_candidate(p_itm=0.5)
        record_predictions([c2], db_path=pred_db)
        assert Prediction.select().count() == 1
        pred = Prediction.get()
        assert abs(pred.p_itm - 0.5) < 0.001

    def test_empty_list(self, pred_db):
        assert record_predictions([], db_path=pred_db) == 0

    def test_skips_no_contract_symbol(self, pred_db):
        c = _make_candidate(contract_symbol="")
        assert record_predictions([c], db_path=pred_db) == 0


class TestComputeBrierScore:
    def test_known_brier(self, pred_db):
        """p_itm=0.8, outcome=True → (0.8 - 1.0)^2 = 0.04."""
        Prediction.create(
            contract_symbol="TEST1",
            ticker="AAPL",
            strike=150.0,
            expiration=date.today() - timedelta(days=1),
            scan_date=date.today(),
            underlying_price_at_scan=145.0,
            p_itm=0.8,
            outcome=True,
            resolved_at=datetime.now(),
        )
        score = compute_brier_score(days=30, db_path=pred_db)
        assert score is not None
        assert abs(score - 0.04) < 0.0001

    def test_no_data_returns_none(self, pred_db):
        assert compute_brier_score(days=30, db_path=pred_db) is None

    def test_multiple_predictions(self, pred_db):
        # (0.8 - 1)^2 = 0.04, (0.2 - 0)^2 = 0.04 → mean = 0.04
        Prediction.create(
            contract_symbol="A", ticker="A", strike=100, expiration=date.today() - timedelta(days=1),
            scan_date=date.today(), underlying_price_at_scan=95, p_itm=0.8, outcome=True, resolved_at=datetime.now(),
        )
        Prediction.create(
            contract_symbol="B", ticker="B", strike=100, expiration=date.today() - timedelta(days=1),
            scan_date=date.today(), underlying_price_at_scan=95, p_itm=0.2, outcome=False, resolved_at=datetime.now(),
        )
        score = compute_brier_score(days=30, db_path=pred_db)
        assert score is not None
        assert abs(score - 0.04) < 0.0001


class TestGetCalibrationSummary:
    def test_returns_correct_keys(self, pred_db):
        summary = get_calibration_summary(days=30, db_path=pred_db)
        assert set(summary.keys()) == {"brier_score", "n_predictions", "n_resolved", "mean_p_itm", "hit_rate"}

    def test_with_data(self, pred_db):
        Prediction.create(
            contract_symbol="X", ticker="X", strike=50, expiration=date.today() - timedelta(days=1),
            scan_date=date.today(), underlying_price_at_scan=48, p_itm=0.6, outcome=True, resolved_at=datetime.now(),
        )
        summary = get_calibration_summary(days=30, db_path=pred_db)
        assert summary["n_predictions"] == 1
        assert summary["n_resolved"] == 1
        assert summary["hit_rate"] == 1.0


class TestResolveOutcomes:
    @patch("yfinance.Ticker")
    def test_no_unresolved(self, mock_ticker_cls, pred_db):
        count = resolve_outcomes(db_path=pred_db)
        assert count == 0
        mock_ticker_cls.assert_not_called()

    @patch("yfinance.Ticker")
    def test_resolves_expired(self, mock_ticker_cls, pred_db):
        mock_ticker = MagicMock()
        mock_ticker.fast_info.last_price = 160.0
        mock_ticker_cls.return_value = mock_ticker

        Prediction.create(
            contract_symbol="R1", ticker="AAPL", strike=150.0,
            expiration=date.today() - timedelta(days=1),
            scan_date=date.today() - timedelta(days=5),
            underlying_price_at_scan=145.0, p_itm=0.6,
        )
        count = resolve_outcomes(db_path=pred_db)
        assert count == 1
        pred = Prediction.get()
        assert pred.outcome is True  # 160 > 150
        assert pred.resolved_at is not None
