# db_manager.py
import sqlite3
import csv
import json
from pathlib import Path
from datetime import datetime

# ----------------------------
# CONFIG
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "databases"
DB_PATH = DB_DIR / "jitter.db"


# ----------------------------
# SETUP
# ----------------------------
def get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


# ----------------------------
# CREATE TABLES
# ----------------------------
def create_tables():
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_name TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            os              TEXT,
            os_release      TEXT,
            cpu             TEXT,
            python_version  TEXT,
            num_runs        INTEGER,
            stress_mode     INTEGER,
            cpu_pinned      INTEGER,
            snapshot_hash   TEXT,
            snapshot_folder TEXT,
            snapshot_id     INTEGER,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER NOT NULL,
            run_number   INTEGER NOT NULL,
            time_seconds REAL NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)

    # ----------------------------
    # EXPERIMENT REGISTRY TABLE
    # Single source of truth for all experiment definitions.
    # Replaces the hardcoded EXPERIMENTS lists that previously
    # lived in batch_run.py, compare.py, and paper_figures.py.
    # ----------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS experiment_registry (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_name TEXT UNIQUE NOT NULL,
            description     TEXT,
            args            TEXT,
            execution_mode  TEXT,
            enabled         INTEGER DEFAULT 1,
            created_at      TEXT NOT NULL
        )
    """)

    # ----------------------------
    # SNAPSHOTS TABLE
    # Records every snapshot created by snapshot.py.
    # Runs link to snapshots via snapshot_id so any result
    # can be traced forward to the archive that captured it.
    # ----------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            folder     TEXT NOT NULL,
            hash       TEXT NOT NULL,
            git_commit TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # ----------------------------
    # PLOTS TABLE
    # Records every plot file written by compare.py and
    # paper_figures.py, linked to the experiment that
    # produced it. Enables forward tracing from a run
    # to all outputs it generated.
    # ----------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_name TEXT,
            plot_type       TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            source_script   TEXT NOT NULL,
            created_at      TEXT NOT NULL
        )
    """)

    # ----------------------------
    # STATISTICAL TESTS TABLE
    # Stores pairwise hypothesis test results produced by
    # stats.py. One row per experiment pair per pipeline run.
    # Includes both parametric (Welch) and non-parametric
    # (Mann-Whitney) results, effect size, and CIs.
    # ----------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS statistical_tests (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_a   TEXT NOT NULL,
            experiment_b   TEXT NOT NULL,
            n_a            INTEGER,
            n_b            INTEGER,
            mean_a         REAL,
            mean_b         REAL,
            std_a          REAL,
            std_b          REAL,
            ci_a_low       REAL,
            ci_a_high      REAL,
            ci_b_low       REAL,
            ci_b_high      REAL,
            welch_t        REAL,
            welch_p        REAL,
            mannwhitney_u  REAL,
            mannwhitney_p  REAL,
            cohens_d       REAL,
            effect_size    TEXT,
            significant    INTEGER,
            created_at     TEXT NOT NULL
        )
    """)

    # ----------------------------
    # ANOMALY FLAGS TABLE
    # Stores per-run anomaly detection results produced by
    # anomaly.py. One row per run per pipeline execution.
    # is_anomaly is the Isolation Forest verdict.
    # z_score_flag is the secondary Z-score signal.
    # high_confidence is true when both methods agree.
    # features_json stores the 7-dim feature vector used.
    # ----------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_flags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL,
            experiment_name TEXT NOT NULL,
            contamination   REAL NOT NULL,
            anomaly_score   REAL NOT NULL,
            z_score         REAL NOT NULL,
            is_anomaly      INTEGER NOT NULL,
            z_score_flag    INTEGER NOT NULL,
            high_confidence INTEGER NOT NULL,
            features_json   TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)

    con.commit()
    con.close()
    print(f"[DB] Tables ready at: {DB_PATH}")


# ----------------------------
# REGISTER EXPERIMENT
# Inserts an experiment definition into the registry.
# INSERT OR IGNORE means re-running the pipeline never
# duplicates a definition — safe to call every startup.
# ----------------------------
def register_experiment(name, description, args, execution_mode):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO experiment_registry
            (experiment_name, description, args, execution_mode, enabled, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
    """, (
        name,
        description,
        json.dumps(args),
        execution_mode,
        datetime.now().isoformat()
    ))

    con.commit()
    con.close()


# ----------------------------
# GET EXPERIMENTS
# Returns all enabled experiments from the registry
# as a list of dicts in the same format as the old
# hardcoded list: [{"name": "baseline", "args": []}, ...]
# All scripts consume this format — nothing else changes.
# ----------------------------
def get_experiments():
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT experiment_name, args
        FROM experiment_registry
        WHERE enabled = 1
        ORDER BY id ASC
    """)

    rows = cur.fetchall()
    con.close()

    experiments = []
    for name, args_json in rows:
        try:
            args = json.loads(args_json)
        except Exception:
            args = []
        experiments.append({"name": name, "args": args})

    return experiments


# ----------------------------
# SEED DEFAULT EXPERIMENTS
# Called once at startup by batch_run.py.
# Registers the three standard experiments if they don't
# already exist. To add a new experiment in the future,
# add one more register_experiment() call here — no other
# file needs to change.
# ----------------------------
def seed_default_experiments():
    register_experiment(
        name="baseline",
        description="Standard unmodified runtime measurement. No stress, no CPU pinning.",
        args=[],
        execution_mode="baseline"
    )

    register_experiment(
        name="stress_test",
        description="High-load runtime measurement with 4x workload to simulate system stress.",
        args=["--stress"],
        execution_mode="stress"
    )

    register_experiment(
        name="cpu_pinned_0",
        description="Runtime measurement pinned to CPU core 0 to reduce scheduler jitter.",
        args=["--cpu", "0"],
        execution_mode="pinned"
    )

    print("[DB] Default experiments seeded into registry")


# ----------------------------
# INSERT SNAPSHOT
# Called by snapshot.py after a snapshot is created.
# Returns the new snapshot_id so it can be stamped
# onto all runs that were active during this pipeline.
# ----------------------------
def insert_snapshot(name, folder, hash_, git_commit):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        INSERT INTO snapshots (name, folder, hash, git_commit, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        name,
        str(folder),
        hash_,
        git_commit,
        datetime.now().isoformat()
    ))

    snapshot_id = cur.lastrowid
    con.commit()
    con.close()

    print(f"[DB] Snapshot recorded: id={snapshot_id}  hash={hash_[:12]}...")
    return snapshot_id


# ----------------------------
# STAMP SNAPSHOT ON RUNS
# After a snapshot is created, links every run from this
# pipeline execution to that snapshot by updating snapshot_id.
# We match by snapshot_folder so we only update runs from
# this specific pipeline execution, not all historical runs.
# ----------------------------
def stamp_snapshot_on_runs(snapshot_folder, snapshot_id):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        UPDATE runs
        SET snapshot_id = ?
        WHERE snapshot_folder = ?
    """, (snapshot_id, str(snapshot_folder)))

    updated = cur.rowcount
    con.commit()
    con.close()

    print(f"[DB] Stamped snapshot_id={snapshot_id} onto {updated} run(s)")


# ----------------------------
# INSERT PLOT
# Called by compare.py and paper_figures.py after each
# plot file is saved. Records the file path, which experiment
# produced it, and which script generated it.
# experiment_name is None for comparison plots that
# aggregate across all experiments.
# ----------------------------
def insert_plot(experiment_name, plot_type, file_path, source_script):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        INSERT INTO plots (experiment_name, plot_type, file_path, source_script, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        experiment_name,
        plot_type,
        str(file_path),
        source_script,
        datetime.now().isoformat()
    ))

    con.commit()
    con.close()


# ----------------------------
# INSERT RUN
# ----------------------------
def insert_run(meta):
    con = get_connection()
    cur = con.cursor()

    args = meta.get("args", {})

    cur.execute("""
        INSERT INTO runs (
            experiment_name,
            timestamp,
            os,
            os_release,
            cpu,
            python_version,
            num_runs,
            stress_mode,
            cpu_pinned,
            snapshot_hash,
            snapshot_folder
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        meta.get("experiment"),
        meta.get("timestamp"),
        meta.get("os"),
        meta.get("os_release"),
        meta.get("cpu"),
        meta.get("python_version"),
        meta.get("num_runs"),
        int(args.get("stress", False)),
        args.get("cpu"),
        meta.get("snapshot_hash"),
        meta.get("snapshot_folder")
    ))

    run_id = cur.lastrowid
    con.commit()
    con.close()

    return run_id


# ----------------------------
# INSERT MEASUREMENTS
# ----------------------------
def insert_measurements(run_id, csv_path):
    con = get_connection()
    cur = con.cursor()

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = [
            (run_id, int(row["run"]), float(row["time_seconds"]))
            for row in reader
        ]

    cur.executemany("""
        INSERT INTO measurements (run_id, run_number, time_seconds)
        VALUES (?, ?, ?)
    """, rows)

    con.commit()
    con.close()

    print(f"[DB] Inserted {len(rows)} measurements for run_id={run_id}")


# ----------------------------
# CHECK IF RUN EXISTS
# ----------------------------
def run_already_imported(meta):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT id FROM runs
        WHERE experiment_name = ?
        AND timestamp = ?
    """, (
        meta.get("experiment"),
        meta.get("timestamp")
    ))

    result = cur.fetchone()
    con.close()

    return result is not None


# ----------------------------
# IMPORT RUN
# ----------------------------
def import_run(csv_path, meta_path):
    csv_path  = Path(csv_path)
    meta_path = Path(meta_path)

    if not csv_path.exists() or not meta_path.exists():
        return

    with open(meta_path, "r") as f:
        meta = json.load(f)

    if run_already_imported(meta):
        print(f"[DB] Skipping (already imported): {meta.get('experiment')} @ {meta.get('timestamp')}")
        return

    run_id = insert_run(meta)
    insert_measurements(run_id, csv_path)

    print(f"[DB] Imported run: {meta.get('experiment')} -> run_id={run_id}")


# ----------------------------
# IMPORT ALL
# ----------------------------
def import_all():
    results_dir = PROJECT_ROOT / "results"

    if not results_dir.exists():
        print("[WARN] No results folder found")
        return

    csv_files = sorted(results_dir.rglob("*.csv"))

    if not csv_files:
        print("[WARN] No CSV files found in results/")
        return

    print(f"\n[DB] Found {len(csv_files)} CSV files to import")

    for csv_path in csv_files:
        stem      = csv_path.stem
        meta_path = csv_path.parent / f"{stem}_meta.json"
        import_run(csv_path, meta_path)


# ----------------------------
# LATEX EXPORT
# ----------------------------
def export_latex_table(output_path="paper_figures/results_table.tex"):
    con = get_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT r.experiment_name,
               AVG(m.time_seconds),
               MIN(m.time_seconds),
               MAX(m.time_seconds),
               COUNT(m.time_seconds)
        FROM runs r
        JOIN measurements m ON r.id = m.run_id
        GROUP BY r.experiment_name
    """)

    rows = cur.fetchall()
    con.close()

    latex = []
    latex.append("\\begin{tabular}{lcccc}")
    latex.append("Experiment & Mean & Min & Max & N \\\\")
    latex.append("\\hline")

    for name, mean, mn, mx, n in rows:
        latex.append(f"{name} & {mean:.4f} & {mn:.4f} & {mx:.4f} & {n} \\\\")

    latex.append("\\end{tabular}")

    out = PROJECT_ROOT / output_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(latex))

    print(f"[LATEX] Exported to {out}")


# ----------------------------
# PRINT SUMMARY
# ----------------------------
def print_summary():
    con = get_connection()
    cur = con.cursor()

    print("\n=== DATABASE SUMMARY ===")

    cur.execute("SELECT COUNT(*) FROM runs")
    print(f"Total runs        : {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM measurements")
    print(f"Total measurements: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM snapshots")
    print(f"Total snapshots   : {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM plots")
    print(f"Total plots       : {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM statistical_tests")
    print(f"Total stat tests  : {cur.fetchone()[0]}")

    print("\n--- Runs by experiment ---")
    cur.execute("""
        SELECT experiment_name, COUNT(*) as run_count
        FROM runs
        GROUP BY experiment_name
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<20} {row[1]} runs")

    # ----------------------------
    # REGISTRY SUMMARY
    # Shows what experiments are currently registered
    # and whether they are enabled or disabled.
    # ----------------------------
    print("\n--- Experiment Registry ---")
    cur.execute("""
        SELECT experiment_name, execution_mode, enabled, description
        FROM experiment_registry
        ORDER BY id ASC
    """)
    for row in cur.fetchall():
        status = "ON " if row[2] else "OFF"
        print(f"  [{status}] {row[0]:<20} ({row[1]}) — {row[3]}")

    # ----------------------------
    # PROVENANCE HEALTH
    # Shows how many runs have been linked to a snapshot,
    # giving a quick health check on provenance completeness.
    # ----------------------------
    print("\n--- Provenance Health ---")
    cur.execute("SELECT COUNT(*) FROM runs WHERE snapshot_id IS NOT NULL")
    linked = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM runs")
    total = cur.fetchone()[0]
    print(f"  Runs linked to a snapshot    : {linked} / {total}")

    cur.execute("SELECT COUNT(DISTINCT experiment_name) FROM plots")
    print(f"  Experiments with plots logged: {cur.fetchone()[0]}")

    # ----------------------------
    # STATS SUMMARY
    # Shows the most recent significant pairwise findings.
    # ----------------------------
    print("\n--- Statistical Tests (latest) ---")
    cur.execute("""
        SELECT experiment_a, experiment_b, welch_p, cohens_d, effect_size, significant
        FROM statistical_tests
        ORDER BY created_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if not rows:
        print("  No tests recorded yet")
    else:
        for row in rows:
            sig = "YES" if row[5] else "NO"
            print(f"  {row[0]:<18} vs {row[1]:<18} "
                  f"p={row[2]:.4f}  d={row[3]:.3f} ({row[4]})  sig={sig}")

    # ----------------------------
    # ANOMALY SUMMARY
    # Quick health check on the most recent anomaly scan.
    # ----------------------------
    print("\n--- Anomaly Detection (latest) ---")
    cur.execute("""
        SELECT experiment_name,
               COUNT(*)        as total,
               SUM(is_anomaly) as flagged,
               SUM(high_confidence) as high_conf
        FROM anomaly_flags
        GROUP BY experiment_name
        ORDER BY experiment_name ASC
    """)
    rows = cur.fetchall()
    if not rows:
        print("  No anomaly scans recorded yet")
    else:
        for row in rows:
            print(f"  {row[0]:<20} total={row[1]}  "
                  f"flagged={row[2]}  high_confidence={row[3]}")

    con.close()


# ----------------------------
# MAIN
# ----------------------------
def main():
    print("[DB] Initializing database...")
    create_tables()
    seed_default_experiments()
    import_all()
    print_summary()
    export_latex_table()
    print(f"\n[DB] Done. Database saved to: {DB_PATH}")


if __name__ == "__main__":
    main()