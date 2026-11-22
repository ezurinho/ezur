from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.market.csv_data import validate_dataset

START = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)


def _write(path: Path, rows: list[tuple[str, str, float]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        for stamp, symbol, price in rows:
            writer.writerow([stamp, symbol, price, price + 0.5, price - 0.5, price + 0.25, 10])
    return path


def test_valid_dataset_passes(tmp_path):
    rows = []
    for index in range(5):
        stamp = (START + timedelta(minutes=index)).isoformat()
        for offset, symbol in enumerate(("AAA", "BBB")):
            rows.append((stamp, symbol, 100.0 + index + offset))
    report = validate_dataset(_write(tmp_path / "ok.csv", rows), ["AAA", "BBB"])
    assert report.ok is True
    assert report.errors == []
    assert report.rows == 10
    assert report.sessions == 1


def test_misaligned_timestamps_flagged(tmp_path):
    rows = []
    for index in range(3):
        stamp = (START + timedelta(minutes=index)).isoformat()
        rows.append((stamp, "AAA", 100.0 + index))
        if index < 2:
            rows.append((stamp, "BBB", 200.0 + index))
    report = validate_dataset(_write(tmp_path / "bad.csv", rows), ["AAA", "BBB"])
    assert report.ok is False
    assert "misaligned" in [issue.code for issue in report.errors]


def test_unknown_symbol_flagged(tmp_path):
    rows = [(START.isoformat(), "AAA", 100.0), (START.isoformat(), "ZZZ", 100.0)]
    report = validate_dataset(_write(tmp_path / "unknown.csv", rows), ["AAA"])
    assert report.ok is False
    assert "unknown_symbol" in [issue.code for issue in report.errors]


def test_empty_symbol_flagged(tmp_path):
    rows = [(START.isoformat(), "AAA", 100.0)]
    report = validate_dataset(_write(tmp_path / "empty.csv", rows), ["AAA", "BBB"])
    assert report.ok is False
    assert "empty_symbol" in [issue.code for issue in report.errors]


def test_missing_file_flagged(tmp_path):
    report = validate_dataset(tmp_path / "nope.csv", ["AAA"])
    assert report.ok is False
    assert report.errors[0].code == "missing_file"


def test_missing_columns_flagged(tmp_path):
    path = tmp_path / "narrow.csv"
    path.write_text("ts,symbol,o\n2026-01-15T14:30:00Z,AAA,1\n", encoding="utf-8")
    report = validate_dataset(path, ["AAA"])
    assert report.ok is False
    assert report.errors[0].code == "missing_columns"


def test_duplicate_timestamps_flagged(tmp_path):
    stamp = START.isoformat()
    rows = [(stamp, "AAA", 100.0), (stamp, "AAA", 101.0)]
    report = validate_dataset(_write(tmp_path / "dup.csv", rows), ["AAA"])
    assert report.ok is False
    assert "duplicate_ts" in [issue.code for issue in report.errors]


def test_report_is_serialisable(tmp_path):
    rows = [(START.isoformat(), "AAA", 100.0)]
    report = validate_dataset(_write(tmp_path / "small.csv", rows), ["AAA"])
    payload = report.as_dict()
    assert payload["ok"] is True
    assert payload["symbols"] == ["AAA"]
