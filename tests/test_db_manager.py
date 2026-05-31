# test_df_manager.py
import pytest
import sqlite3
import csv
import json
import sys
from pathlib import Path

# make sure the scripts folder is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import db_manager

# ----------------------------
# FIXTURES
# ----------------------------
@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """
    Redirects db_manager to use a temporary database
    for each test so we never touch the real jitter.db
    """
    db_dir = tmp_path / "databases"
    db_dir.mkdir()
    db_path = db_dir / "test_jitter.db"

    monkeypatch.setattr(db_manager, "DB_DIR", db_dir)
    monkeypatch.setattr(db_manager, "DB_PATH", db_path)

    db_manager.create_tables()
    return db_path


@pytest.fixture
def sample_meta():
    return {
        "experiment": "baseline",
        "timestamp": "2026-05-21T18:00:00",
        "os": "Darwin",
        "os_release": "24.0.0",
        "cpu": "Apple M1",
        "python_version": "3.11.0",
        "num_runs": 5,
        "args": {
            "stress": False,
            "cpu": None
        }
    }


@pytest.fixture
def sample_csv(tmp_path):
    csv_path = tmp_path / "baseline_20260521_180000.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "time_seconds"])
        for i in range(5):
            writer.writerow([i, 0.006 + i * 0.0001])
    return csv_path


@pytest.fixture
def sample_meta_file(tmp_path, sample_meta):
    meta_path = tmp_path / "baseline_20260521_180000_meta.json"
    with open(meta_path, "w") as f:
        json.dump(sample_meta, f)
    return meta_path


# ----------------------------
# TESTS: CREATE TABLES
# ----------------------------
def test_tables_created(tmp_db):
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    con.close()

    assert "runs" in tables
    assert "measurements" in tables
    assert "experiment_registry" in tables


# ----------------------------
# TESTS: INSERT RUN
# ----------------------------
def test_insert_run(tmp_db, sample_meta):
    run_id = db_manager.insert_run(sample_meta)

    assert run_id is not None
    assert isinstance(run_id, int)
    assert run_id > 0

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT experiment_name, timestamp FROM runs WHERE id = ?", (run_id,))
    row = cur.fetchone()
    con.close()

    assert row is not None
    assert row[0] == "baseline"
    assert row[1] == "2026-05-21T18:00:00"


def test_insert_run_stress_mode(tmp_db):
    meta = {
        "experiment": "stress_test",
        "timestamp": "2026-05-21T19:00:00",
        "os": "Darwin",
        "os_release": "24.0.0",
        "cpu": "Apple M1",
        "python_version": "3.11.0",
        "num_runs": 200,
        "args": {"stress": True, "cpu": None}
    }

    run_id = db_manager.insert_run(meta)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT stress_mode FROM runs WHERE id = ?", (run_id,))
    row = cur.fetchone()
    con.close()

    assert row[0] == 1


# ----------------------------
# TESTS: INSERT MEASUREMENTS
# ----------------------------
def test_insert_measurements(tmp_db, sample_meta, sample_csv):
    run_id = db_manager.insert_run(sample_meta)
    db_manager.insert_measurements(run_id, sample_csv)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM measurements WHERE run_id = ?", (run_id,))
    count = cur.fetchone()[0]
    con.close()

    assert count == 5


def test_measurements_values(tmp_db, sample_meta, sample_csv):
    run_id = db_manager.insert_run(sample_meta)
    db_manager.insert_measurements(run_id, sample_csv)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("""
        SELECT run_number, time_seconds
        FROM measurements
        WHERE run_id = ?
        ORDER BY run_number ASC
    """, (run_id,))
    rows = cur.fetchall()
    con.close()

    assert rows[0][0] == 0
    assert abs(rows[0][1] - 0.006) < 1e-9
    assert rows[4][0] == 4
    assert abs(rows[4][1] - 0.0064) < 1e-9


# ----------------------------
# TESTS: DUPLICATE DETECTION
# ----------------------------
def test_duplicate_detection(tmp_db, sample_meta):
    db_manager.insert_run(sample_meta)

    assert db_manager.run_already_imported(sample_meta) is True


def test_no_false_positive_duplicate(tmp_db, sample_meta):
    different_meta = sample_meta.copy()
    different_meta["timestamp"] = "2026-05-21T20:00:00"

    assert db_manager.run_already_imported(different_meta) is False


def test_import_run_skips_duplicate(tmp_db, sample_meta, sample_csv, sample_meta_file):
    db_manager.import_run(sample_csv, sample_meta_file)
    db_manager.import_run(sample_csv, sample_meta_file)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM runs")
    count = cur.fetchone()[0]
    con.close()

    assert count == 1


# ----------------------------
# TESTS: MISSING FILES
# ----------------------------
def test_import_run_missing_csv(tmp_db, tmp_path, sample_meta_file):
    missing_csv = tmp_path / "nonexistent.csv"
    db_manager.import_run(missing_csv, sample_meta_file)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM runs")
    count = cur.fetchone()[0]
    con.close()

    assert count == 0


def test_import_run_missing_meta(tmp_db, sample_csv, tmp_path):
    missing_meta = tmp_path / "nonexistent_meta.json"
    db_manager.import_run(sample_csv, missing_meta)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM runs")
    count = cur.fetchone()[0]
    con.close()

    assert count == 0