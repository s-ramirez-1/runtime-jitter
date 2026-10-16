# mlflow_export.py
"""Export runs from the SQLite database to MLflow (post-hoc, no changes to measurement).

Set MLFLOW_TRACKING_URI to log to a server; otherwise logs to a local SQLite
backend at <project>/mlflow.db (newer MLflow versions no longer accept the ./mlruns file store).
Runs already exported (tag run_key = experiment|timestamp) are skipped, so this is safe to re-run.
"""
import os

import numpy as np

import db_manager


def main():
    try:
        import mlflow
    except ImportError:
        raise SystemExit("[ERROR] mlflow is not installed. Run: pip install -r requirements-mlflow.txt")

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI")
                            or f"sqlite:///{db_manager.PROJECT_ROOT / 'mlflow.db'}")
    mlflow.set_experiment("runtime-jitter-pipeline")

    con = db_manager.get_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT r.id, r.experiment_name, r.timestamp, r.os, r.cpu, r.python_version, r.num_runs,
               r.stress_mode, r.cpu_pinned, r.workload, r.gpu_name, r.gpu_driver, r.cuda_version,
               r.torch_version, s.hash, s.git_commit
        FROM runs r LEFT JOIN snapshots s ON r.snapshot_id = s.id
    """)
    runs = cur.fetchall()

    exported = 0
    for (rid, name, ts, os_, cpu, py, n, stress, pinned, workload, gpu, driver, cuda, torch_v,
         snap_hash, commit) in runs:
        # Key on experiment + timestamp, not the DB id: ids restart at 1 if the
        # database is deleted (cleanup --delete-db), which would collide.
        run_key = f"{name}|{ts}"
        if mlflow.search_runs(filter_string=f"tags.run_key = '{run_key}'").shape[0]:
            continue
        cur.execute("SELECT time_seconds FROM measurements WHERE run_id=? ORDER BY run_number", (rid,))
        t = np.array([r[0] for r in cur.fetchall()])
        if t.size == 0:
            continue
        p50, p95, p99 = np.percentile(t, [50, 95, 99])
        with mlflow.start_run(run_name=f"{name}_{rid}"):
            mlflow.set_tags({"run_key": run_key, "db_run_id": rid, "workload": workload or "cpu", "snapshot_hash": snap_hash or "",
                             "git_commit": commit or ""})
            mlflow.log_params({k: v for k, v in {
                "experiment": name, "timestamp": ts, "os": os_, "cpu": cpu, "python": py, "num_runs": n,
                "stress": stress, "cpu_pinned": pinned, "gpu": gpu, "gpu_driver": driver, "cuda": cuda,
                "torch": torch_v}.items() if v is not None})
            mlflow.log_metrics({"mean_s": float(t.mean()), "std_s": float(t.std()), "p50_s": float(p50),
                                "p95_s": float(p95), "p99_s": float(p99), "tail_ratio_p99_p50": float(p99 / p50)})
        exported += 1
    con.close()
    print(f"[MLFLOW] Exported {exported} new run(s)")


if __name__ == "__main__":
    main()
