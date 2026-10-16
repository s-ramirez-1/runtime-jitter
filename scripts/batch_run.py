# batch_run.py
import subprocess
import sys
import platform
from datetime import datetime
import os
from pathlib import Path
import hashlib
import argparse
import shutil
import time
import webbrowser

# ============================================================
# PATH RESOLUTION
# ============================================================
SCRIPT_DIR    = Path(__file__).resolve().parent
PROJECT_ROOT  = SCRIPT_DIR.parent
VENV_DIR      = PROJECT_ROOT / ".venv"
REQ_FILE      = PROJECT_ROOT / "requirements.txt"
REQ_HASH_FILE = VENV_DIR / ".requirements.hash"


# ============================================================
# VENV BOOTSTRAP
# ============================================================
def in_venv():
    return sys.prefix != sys.base_prefix


def get_venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def create_venv():
    print("[BOOTSTRAP] Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])


def hash_requirements():
    if not REQ_FILE.exists():
        return None
    return hashlib.sha256(REQ_FILE.read_bytes()).hexdigest()


def requirements_up_to_date():
    if not REQ_HASH_FILE.exists():
        return False
    if not REQ_FILE.exists():
        return True
    return hash_requirements() == REQ_HASH_FILE.read_text().strip()


def install_requirements(python_bin):
    if not REQ_FILE.exists():
        print("[WARN] requirements.txt not found")
        return

    print("[BOOTSTRAP] Installing dependencies...")
    subprocess.check_call([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(python_bin), "-m", "pip", "install", "-r", str(REQ_FILE)])
    REQ_HASH_FILE.write_text(hash_requirements())


def ensure_environment():
    # Inside Docker, Python is installed directly into the container.
    # Skip all venv bootstrap — just return the current Python.
    if os.environ.get("RUNNING_IN_DOCKER"):
        print("[BOOTSTRAP] Running inside Docker — skipping venv setup")
        return sys.executable

    # Already inside a venv — nothing to do
    if in_venv():
        return sys.executable

    python_bin = get_venv_python()

    if not python_bin.exists():
        create_venv()

    python_bin = get_venv_python()

    if not requirements_up_to_date():
        install_requirements(python_bin)
    else:
        print("[BOOTSTRAP] Requirements already up to date — skipping install")

    print("[BOOTSTRAP] Re-launching inside virtual environment...\n")
    subprocess.check_call([str(python_bin)] + sys.argv)
    sys.exit(0)


# ============================================================
# LOAD EXPERIMENTS FROM REGISTRY
# ============================================================
def load_experiments_from_registry(python_bin):
    sys.path.insert(0, str(SCRIPT_DIR))
    import db_manager

    db_manager.create_tables()
    db_manager.seed_default_experiments()

    experiments = db_manager.get_experiments()

    # GPU experiments stay in the registry, but only run where a GPU is visible.
    # (The registry lives in a database that native and Docker runs can share.)
    if not shutil.which("nvidia-smi"):
        gpu_names = [e["name"] for e in experiments
                     if db_manager.experiment_workload(e) == "gpu"]
        if gpu_names:
            print(f"[REGISTRY] No NVIDIA GPU detected — skipping: {', '.join(gpu_names)}")
        experiments = [e for e in experiments
                       if db_manager.experiment_workload(e) != "gpu"]

    print(f"\n[REGISTRY] Loaded {len(experiments)} experiment(s) from registry:")
    for exp in experiments:
        print(f"  - {exp['name']}  args: {exp['args']}")

    return experiments


# ============================================================
# CLEANUP STEP
# ============================================================
def run_cleanup(python_bin, args):
    cleanup_script = SCRIPT_DIR / "cleanup_files.py"

    if not cleanup_script.exists():
        print("[WARN] cleanup_files.py not found — skipping cleanup")
        return True

    if not args.clean:
        print("[INFO] Cleanup skipped (use --clean to enable)")
        return True

    cmd = [
        python_bin,
        str(cleanup_script),
        str(PROJECT_ROOT),
    ]

    if args.delete_db:
        cmd.append("--delete-db")
    if args.delete_tex:
        cmd.append("--delete-tex")
    if args.delete_snapshots:
        cmd.append("--delete-snapshots")

    print("\n==============================")
    print("[RUN] Cleanup Step")
    print("==============================")
    print(f"[CMD] {' '.join(map(str, cmd))}")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] Cleanup completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Cleanup failed (code {e.returncode})")
        return False


# ============================================================
# RUN EXPERIMENTS
# ============================================================
def run_experiment(exp, python_bin):
    name = exp["name"]
    args = exp["args"]

    cmd = [
        python_bin,
        str(SCRIPT_DIR / "BaselineRuntime_JitterMeasurement.py"),
        "--name",
        name
    ] + args

    print("\n==============================")
    print(f"[RUN] Experiment: {name}")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print(f"[OK] Completed: {name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed: {name} (code {e.returncode})")
        return False


# ============================================================
# ANALYSIS
# ============================================================
def run_analysis(python_bin):
    cmd = [python_bin, str(SCRIPT_DIR / "compare.py")]

    print("\n==============================")
    print("[RUN] Analysis (compare.py)")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] compare.py completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] compare.py failed (code {e.returncode})")
        return False


# ============================================================
# DATABASE IMPORT STEP
# ============================================================
def run_database_import(python_bin):
    cmd = [python_bin, str(SCRIPT_DIR / "db_manager.py")]

    print("\n==============================")
    print("[RUN] Database Import (db_manager.py)")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] db_manager.py completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] db_manager.py failed (code {e.returncode})")
        return False


# ============================================================
# MLFLOW EXPORT (optional, enabled with --mlflow)
# ============================================================
def run_mlflow_export(python_bin):
    cmd = [python_bin, str(SCRIPT_DIR / "mlflow_export.py")]

    print("\n==============================")
    print("[RUN] MLflow Export (mlflow_export.py)")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] mlflow_export.py completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] mlflow_export.py failed (code {e.returncode})")
        return False


# ============================================================
# STATISTICAL HYPOTHESIS TESTING
# ============================================================
def run_stats(python_bin):
    cmd = [python_bin, str(SCRIPT_DIR / "stats.py")]

    print("\n==============================")
    print("[RUN] Statistical Tests (stats.py)")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] stats.py completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] stats.py failed (code {e.returncode})")
        return False


# ============================================================
# ANOMALY DETECTION
# ============================================================
def run_anomaly(python_bin):
    cmd = [python_bin, str(SCRIPT_DIR / "anomaly.py")]

    print("\n==============================")
    print("[RUN] Anomaly Detection (anomaly.py)")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] anomaly.py completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] anomaly.py failed (code {e.returncode})")
        return False


# ============================================================
# FIGURES
# ============================================================
def run_figures(python_bin):
    cmd = [python_bin, str(SCRIPT_DIR / "paper_figures.py")]

    print("\n==============================")
    print("[RUN] Paper Figures")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] paper_figures.py completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] paper_figures.py failed (code {e.returncode})")
        return False


# ============================================================
# SNAPSHOT STEP
# ============================================================
def run_snapshot(python_bin):
    snapshot_file = SCRIPT_DIR / "snapshot.py"

    if not snapshot_file.exists():
        return True

    cmd = [python_bin, str(snapshot_file), "--name", "pipeline"]

    print("\n==============================")
    print("[RUN] Snapshot")
    print("==============================")

    try:
        subprocess.run(cmd, check=True)
        print("[OK] Snapshot completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Snapshot failed (code {e.returncode})")
        return False


# ============================================================
# DASHBOARD STEP
# ============================================================
def prompt_dashboard_update(python_bin):
    while True:
        response = input("\n[DASHBOARD] Would you like to launch the dashboard? (y/n): ").strip().lower()
        if response == "y":
            dashboard_dir = PROJECT_ROOT / "dashboard"
            dashboard_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                python_bin, "-m", "streamlit", "run",
                str(SCRIPT_DIR / "dashboard.py"),
                "--server.headless", "true",
                "--server.port", "8501",
                "--server.address", "0.0.0.0",
            ]

            print("\n==============================")
            print("[RUN] Launching Dashboard")
            print("[INFO] Open http://localhost:8501 in your browser")
            print("==============================")

            if os.environ.get("RUNNING_IN_DOCKER"):
                # In Docker: run in foreground so the container
                # stays alive and the port remains open
                subprocess.run(cmd)
            else:
                # Native: launch in background and open browser
                subprocess.Popen(cmd)
                print("[INFO] Waiting for Streamlit to start...")
                time.sleep(5)
                webbrowser.open("http://localhost:8501")
                print("[OK] Dashboard launched — check your browser at http://localhost:8501")
            return
        elif response == "n":
            print("[INFO] Dashboard skipped")
            return
        else:
            print("[INPUT] Invalid input, please answer y/n")


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean",            action="store_true", help="Run cleanup before pipeline")
    parser.add_argument("--delete-db",        action="store_true")
    parser.add_argument("--delete-tex",       action="store_true")
    parser.add_argument("--delete-snapshots", action="store_true")
    parser.add_argument("--mlflow",           action="store_true", help="Export runs to MLflow after DB import")
    args = parser.parse_args()

    python_bin = ensure_environment()

    print("\n====================================")
    print("  EXPERIMENT PIPELINE START")
    print("====================================")
    print(f"[INFO] OS: {platform.system()}")
    print(f"[INFO] Time: {datetime.now()}")
    print(f"[INFO] Project Root: {PROJECT_ROOT}")
    print(f"[INFO] Script Dir: {SCRIPT_DIR}")
    print("====================================")

    # 1. CLEANUP
    if not run_cleanup(python_bin, args):
        print("[STOP] Cleanup failed — aborting pipeline.")
        return

    # 2. LOAD REGISTRY
    experiments = load_experiments_from_registry(python_bin)

    if not experiments:
        print("[STOP] No enabled experiments found in registry — aborting.")
        return

    # 3. RUN EXPERIMENTS
    for exp in experiments:
        if not run_experiment(exp, python_bin):
            print("[STOP] Experiment failed — aborting pipeline.")
            return

    # 4. ANALYSIS
    if not run_analysis(python_bin):
        print("[STOP] Analysis failed — aborting pipeline.")
        return

    # 5. DB IMPORT
    if not run_database_import(python_bin):
        print("[STOP] DB import failed — aborting pipeline.")
        return

    # 5b. MLFLOW EXPORT (optional)
    if args.mlflow:
        if not run_mlflow_export(python_bin):
            print("[WARN] MLflow export failed — continuing pipeline.")

    # 6. STATISTICAL TESTS
    if not run_stats(python_bin):
        print("[WARN] Stats step failed — continuing pipeline.")

    # 7. ANOMALY DETECTION
    if not run_anomaly(python_bin):
        print("[WARN] Anomaly detection failed or skipped — continuing pipeline.")

    # 8. FIGURES
    if not run_figures(python_bin):
        print("[STOP] Figure generation failed.")
        return

    # 9. SNAPSHOT
    if not run_snapshot(python_bin):
        print("[STOP] Snapshot failed — aborting pipeline.")
        return

    # 10. DASHBOARD
    prompt_dashboard_update(python_bin)

    print("\n====================================")
    print("  PIPELINE COMPLETE")
    print("====================================")


if __name__ == "__main__":
    main()
