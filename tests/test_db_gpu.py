import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import db_manager  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_manager, "DB_DIR", tmp_path)
    monkeypatch.setattr(db_manager, "DB_PATH", tmp_path / "test.db")
    return db_manager


def _write_run(folder, name, ts, workload="cpu", gpu=None, samples=None):
    stem = f"{name}_{ts}"
    csv_path = folder / f"{stem}.csv"
    csv_path.write_text("run,time_seconds\n0,0.5\n1,0.6\n2,0.7\n")
    meta = {"experiment": name, "timestamp": f"2026-10-01T00:00:0{ts[-1]}", "os": "Linux", "num_runs": 3,
            "args": {"stress": False, "cpu": None}, "workload": workload, "gpu": gpu}
    meta_path = folder / f"{stem}_meta.json"
    meta_path.write_text(json.dumps(meta))
    if samples:
        (folder / f"{stem}_gpu.json").write_text(json.dumps({"interval_s": 0.25, "samples": samples}))
    return csv_path, meta_path


def test_existing_database_is_migrated_in_place(db, tmp_path):
    # Simulate a database created BEFORE the GPU columns existed.
    con = sqlite3.connect(tmp_path / "test.db")
    con.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, experiment_name TEXT NOT NULL, "
                "timestamp TEXT NOT NULL, snapshot_id INTEGER)")
    con.execute("INSERT INTO runs (experiment_name, timestamp) VALUES ('old', 't0')")
    con.commit()
    con.close()

    db.create_tables()
    db.create_tables()  # idempotent

    con = sqlite3.connect(tmp_path / "test.db")
    cols = [r[1] for r in con.execute("PRAGMA table_info(runs)")]
    assert {"workload", "gpu_name", "gpu_driver", "cuda_version", "torch_version"} <= set(cols)
    assert con.execute("SELECT workload FROM runs WHERE experiment_name='old'").fetchone()[0] == "cpu"
    con.close()


def test_cpu_run_defaults_to_cpu_workload(db, tmp_path):
    db.create_tables()
    c, m = _write_run(tmp_path, "baseline", "20261001_000001")
    db.import_run(c, m)
    con = sqlite3.connect(tmp_path / "test.db")
    assert con.execute("SELECT workload, gpu_name FROM runs").fetchone() == ("cpu", None)
    assert con.execute("SELECT COUNT(*) FROM gpu_samples").fetchone()[0] == 0


def test_gpu_run_imports_samples_and_metadata(db, tmp_path):
    db.create_tables()
    gpu = {"gpu_names": ["RTX 4090"], "driver_version": "555.1", "cuda_version": "12.1", "torch": "2.4.0"}
    samples = [{"ts": 1.0, "gpu_idx": 0, "util_pct": 90.0, "mem_mib": 2000.0, "power_w": 300.0,
                "temp_c": 65.0, "sm_mhz": 2500.0},
               {"ts": 1.25, "gpu_idx": 0, "util_pct": None, "mem_mib": 2001.0, "power_w": None,
                "temp_c": 66.0, "sm_mhz": 2490.0}]
    c, m = _write_run(tmp_path, "gpu_baseline", "20261001_000002", workload="gpu", gpu=gpu, samples=samples)
    db.import_run(c, m)

    con = sqlite3.connect(tmp_path / "test.db")
    row = con.execute("SELECT workload, gpu_name, gpu_driver, cuda_version, torch_version FROM runs").fetchone()
    assert row == ("gpu", "RTX 4090", "555.1", "12.1", "2.4.0")
    assert con.execute("SELECT COUNT(*) FROM gpu_samples").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 3


def test_reimport_is_skipped(db, tmp_path):
    db.create_tables()
    c, m = _write_run(tmp_path, "baseline", "20261001_000003")
    db.import_run(c, m)
    db.import_run(c, m)
    con = sqlite3.connect(tmp_path / "test.db")
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_gpu_experiments_registered_only_with_nvidia_smi(db, monkeypatch):
    db.create_tables()
    monkeypatch.setattr(db_manager.shutil, "which", lambda _: None)
    db.seed_default_experiments()
    names = {e["experiment_name"] if isinstance(e, dict) else e for e in
             [r[0] for r in sqlite3.connect(db.DB_PATH).execute("SELECT experiment_name FROM experiment_registry")]}
    assert "gpu_baseline" not in names

    monkeypatch.setattr(db_manager.shutil, "which", lambda _: "/usr/bin/nvidia-smi")
    db.seed_default_experiments()
    names = {r[0] for r in sqlite3.connect(db.DB_PATH).execute("SELECT experiment_name FROM experiment_registry")}
    assert {"gpu_baseline", "gpu_stress", "gpu_pinned_0"} <= names


def test_snapshot_stamps_unlinked_runs_but_not_earlier_ones(db, tmp_path):
    db.create_tables()
    c1, m1 = _write_run(tmp_path, "baseline", "20261001_000004")
    db.import_run(c1, m1)
    first = db.insert_snapshot("pipeline", tmp_path / "snap1", "hash1", "abc")
    db.stamp_snapshot_on_runs(tmp_path / "snap1", first)

    c2, m2 = _write_run(tmp_path, "stress_test", "20261001_000005")
    db.import_run(c2, m2)
    second = db.insert_snapshot("pipeline", tmp_path / "snap2", "hash2", "abc")
    db.stamp_snapshot_on_runs(tmp_path / "snap2", second)

    con = sqlite3.connect(tmp_path / "test.db")
    rows = dict(con.execute("SELECT experiment_name, snapshot_id FROM runs"))
    assert rows == {"baseline": first, "stress_test": second}


def test_experiment_workload_from_args(db):
    assert db.experiment_workload({"name": "baseline", "args": []}) == "cpu"
    assert db.experiment_workload({"name": "s", "args": ["--stress"]}) == "cpu"
    assert db.experiment_workload({"name": "g", "args": ["--workload", "gpu", "--stress"]}) == "gpu"
    assert db.experiment_workload({"name": "x"}) == "cpu"
