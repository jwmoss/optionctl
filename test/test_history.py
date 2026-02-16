"""Tests for the history module."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from optionctl.history import (
    cleanup_old_history,
    compute_vol_vs_avg,
    get_avg_volume,
    get_volume_history,
    record_volume_snapshot,
)

# ---------------------------------------------------------------------------
# record_volume_snapshot
# ---------------------------------------------------------------------------


def test_record_volume_snapshot_creates_file(history_dir, make_candidate):
    c1 = make_candidate(contract_symbol="AAPL260130C00200000", volume=500)
    c2 = make_candidate(contract_symbol="AAPL260130C00210000", volume=300)

    record_volume_snapshot([c1, c2])

    files = list(history_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["AAPL260130C00200000"] == 500
    assert data["AAPL260130C00210000"] == 300


def test_record_volume_snapshot_merges(history_dir, make_candidate):
    c1 = make_candidate(contract_symbol="SYM1", volume=100)
    record_volume_snapshot([c1])

    c2 = make_candidate(contract_symbol="SYM2", volume=200)
    record_volume_snapshot([c2])

    files = list(history_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["SYM1"] == 100
    assert data["SYM2"] == 200


def test_record_volume_snapshot_empty(history_dir):
    record_volume_snapshot([])
    assert not list(history_dir.glob("*.json"))


def test_record_volume_snapshot_skips_empty_symbol(history_dir, make_candidate):
    c = make_candidate(contract_symbol="", volume=500)
    record_volume_snapshot([c])

    if list(history_dir.glob("*.json")):
        data = json.loads(next(iter(history_dir.glob("*.json"))).read_text())
        assert "" not in data


# ---------------------------------------------------------------------------
# get_volume_history
# ---------------------------------------------------------------------------


def test_get_volume_history_returns_past_data(history_dir):
    today = datetime.now(tz=UTC).date()

    for offset in range(1, 4):
        hist_date = today - timedelta(days=offset)
        path = history_dir / f"{hist_date.isoformat()}.json"
        history_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"SYM1": 100 * offset}))

    result = get_volume_history("SYM1", days=5)
    assert len(result) == 3
    assert 100 in result
    assert 200 in result
    assert 300 in result


def test_get_volume_history_missing_symbol(history_dir):
    today = datetime.now(tz=UTC).date()
    hist_date = today - timedelta(days=1)
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / f"{hist_date.isoformat()}.json").write_text(json.dumps({"OTHER": 500}))

    result = get_volume_history("SYM1", days=5)
    assert result == []


def test_get_volume_history_no_files(history_dir):
    assert get_volume_history("SYM1") == []


# ---------------------------------------------------------------------------
# get_avg_volume
# ---------------------------------------------------------------------------


def test_get_avg_volume_sufficient_data(history_dir):
    today = datetime.now(tz=UTC).date()
    history_dir.mkdir(parents=True, exist_ok=True)

    for offset in [1, 2, 3]:
        hist_date = today - timedelta(days=offset)
        (history_dir / f"{hist_date.isoformat()}.json").write_text(
            json.dumps({"SYM1": 100 * offset})
        )

    avg = get_avg_volume("SYM1", days=5)
    assert avg == 200.0  # (100 + 200 + 300) / 3


def test_get_avg_volume_insufficient_data(history_dir):
    today = datetime.now(tz=UTC).date()
    history_dir.mkdir(parents=True, exist_ok=True)
    hist_date = today - timedelta(days=1)
    (history_dir / f"{hist_date.isoformat()}.json").write_text(json.dumps({"SYM1": 100}))

    assert get_avg_volume("SYM1", days=5) is None


def test_get_avg_volume_no_data(history_dir):
    assert get_avg_volume("SYM1") is None


# ---------------------------------------------------------------------------
# compute_vol_vs_avg
# ---------------------------------------------------------------------------


def test_compute_vol_vs_avg_with_baseline(history_dir):
    today = datetime.now(tz=UTC).date()
    history_dir.mkdir(parents=True, exist_ok=True)

    for offset in [1, 2]:
        hist_date = today - timedelta(days=offset)
        (history_dir / f"{hist_date.isoformat()}.json").write_text(json.dumps({"SYM1": 100}))

    result = compute_vol_vs_avg(500, "SYM1", days=5)
    assert result == 5.0  # 500 / 100


def test_compute_vol_vs_avg_no_baseline(history_dir):
    assert compute_vol_vs_avg(500, "UNKNOWN") is None


# ---------------------------------------------------------------------------
# cleanup_old_history
# ---------------------------------------------------------------------------


def test_cleanup_old_history(history_dir):
    history_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(tz=UTC).date()
    old_date = today - timedelta(days=45)
    recent_date = today - timedelta(days=5)

    (history_dir / f"{old_date.isoformat()}.json").write_text("{}")
    (history_dir / f"{recent_date.isoformat()}.json").write_text("{}")

    removed = cleanup_old_history(max_age_days=30)
    assert removed == 1
    assert not (history_dir / f"{old_date.isoformat()}.json").exists()
    assert (history_dir / f"{recent_date.isoformat()}.json").exists()


def test_cleanup_old_history_empty(history_dir):
    assert cleanup_old_history() == 0


def test_cleanup_old_history_invalid_filename(history_dir):
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "not-a-date.json").write_text("{}")

    removed = cleanup_old_history(max_age_days=0)
    assert removed == 0
