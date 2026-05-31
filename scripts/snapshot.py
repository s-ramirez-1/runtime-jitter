# snapshot.py
import subprocess
import json
import shutil
import hashlib
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)

# ----------------------------
# DB MANAGER IMPORT
# We import db_manager directly so snapshot.py can write
# its record into the database as part of creation.
# ----------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db_manager


# ----------------------------
# GIT INFO
# ----------------------------
def get_git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT
        ).decode().strip()
    except Exception:
        return "unknown"


# ----------------------------
# HASH UTILITY
# ----------------------------
def compute_hash(folder: Path):
    sha = hashlib.sha256()

    for path in sorted(folder.rglob("*")):
        if path.is_file():
            try:
                sha.update(path.read_bytes())
            except Exception:
                continue

    return sha.hexdigest()


# ----------------------------
# DB SUMMARY
# ----------------------------
def get_db_summary():
    try:
        import sqlite3

        db_path = PROJECT_ROOT / "databases" / "jitter.db"
        if not db_path.exists():
            return {}

        con = sqlite3.connect(db_path)
        cur = con.cursor()

        cur.execute("SELECT COUNT(*) FROM runs")
        runs = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM measurements")
        measurements = cur.fetchone()[0]

        cur.execute("""
            SELECT experiment_name, COUNT(*)
            FROM runs
            GROUP BY experiment_name
        """)

        per_exp = {r[0]: r[1] for r in cur.fetchall()}

        con.close()

        return {
            "total_runs": runs,
            "total_measurements": measurements,
            "runs_per_experiment": per_exp
        }

    except Exception as e:
        return {"error": str(e)}


# ----------------------------
# EXPERIMENT MANIFEST
# ----------------------------
def get_experiment_manifest():
    try:
        # Pull the live registry instead of importing batch_run,
        # so the manifest always reflects what's actually enabled.
        db_manager.create_tables()
        return db_manager.get_experiments()
    except Exception:
        return []


# ----------------------------
# SNAPSHOT CREATION
# ----------------------------
def create_snapshot(name="run"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    folder = SNAPSHOT_DIR / f"{name}_{timestamp}"
    folder.mkdir(parents=True, exist_ok=True)

    print(f"[SNAPSHOT] Creating snapshot: {folder.name}")

    # 1. Git commit
    git_commit = get_git_commit()
    (folder / "git_commit.txt").write_text(git_commit)

    # 2. Environment
    try:
        pip_freeze = subprocess.check_output(["pip", "freeze"]).decode()
    except Exception:
        pip_freeze = "pip freeze failed"

    (folder / "requirements_snapshot.txt").write_text(pip_freeze)

    # 3. Results
    results = PROJECT_ROOT / "results"
    if results.exists():
        shutil.copytree(results, folder / "results", dirs_exist_ok=True)

    # 4. Plots
    plots = PROJECT_ROOT / "plots"
    if plots.exists():
        shutil.copytree(plots, folder / "plots", dirs_exist_ok=True)

    # 5. LaTeX
    latex_file = PROJECT_ROOT / "paper_figures" / "results_table.tex"
    if latex_file.exists():
        shutil.copy(latex_file, folder / "results_table.tex")

    # 6. DB summary
    db_summary = get_db_summary()
    (folder / "db_summary.json").write_text(json.dumps(db_summary, indent=2))

    # 7. Experiment manifest (now pulled from registry)
    manifest = get_experiment_manifest()
    (folder / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2))

    # 8. Hash
    snapshot_hash = compute_hash(folder)
    (folder / "snapshot_hash.txt").write_text(snapshot_hash)

    print(f"[SNAPSHOT] Hash: {snapshot_hash}")
    print(f"[SNAPSHOT] Saved to: {folder}")

    # ----------------------------
    # PROVENANCE: RECORD SNAPSHOT IN DB
    # Write this snapshot into the snapshots table so runs
    # can be formally linked to it. Then stamp the snapshot_id
    # onto any runs whose snapshot_folder matches this one.
    # ----------------------------
    db_manager.create_tables()

    snapshot_id = db_manager.insert_snapshot(
        name=name,
        folder=str(folder),
        hash_=snapshot_hash,
        git_commit=git_commit
    )

    db_manager.stamp_snapshot_on_runs(
        snapshot_folder=str(folder),
        snapshot_id=snapshot_id
    )

    print(f"[SNAPSHOT] Provenance recorded: snapshot_id={snapshot_id}")

    return {
        "name": name,
        "folder": str(folder),
        "hash": snapshot_hash,
        "timestamp": timestamp,
        "snapshot_id": snapshot_id
    }


# ----------------------------
# CLI ENTRY
# ----------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="run")
    args = parser.parse_args()

    create_snapshot(args.name)