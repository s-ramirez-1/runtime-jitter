# compare.py
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np
import sys

# ----------------------------
# CONFIG
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"
PLOTS_DIR = PROJECT_ROOT / "plots"

# ----------------------------
# LOAD EXPERIMENTS FROM REGISTRY
# Replaces the hardcoded EXPERIMENTS list.
# Falls back gracefully if the DB isn't available yet.
# ----------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import db_manager
    db_manager.create_tables()
    db_manager.seed_default_experiments()
    _registry = db_manager.get_experiments()
    EXPERIMENTS = [exp["name"] for exp in _registry]
except Exception as e:
    print(f"[WARN] Could not load registry, falling back to defaults: {e}")
    EXPERIMENTS = ["baseline", "stress_test", "cpu_pinned_0"]

# ----------------------------
# CREATE DIRECTORIES
# ----------------------------
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

COMPARISON_DIR = PLOTS_DIR / "comparison"
COMPARISON_DIR.mkdir(parents=True, exist_ok=True)

for exp in EXPERIMENTS:
    (PLOTS_DIR / exp).mkdir(parents=True, exist_ok=True)


# ----------------------------
# LOAD EXPERIMENT
# ----------------------------
def load_experiment(exp_name):
    path = RESULTS_DIR / exp_name

    if not path.exists():
        return None

    files = list(path.glob("*.csv"))
    if len(files) == 0:
        return None

    all_times = []

    for f in files:
        try:
            df = pd.read_csv(f)
            if "time_seconds" not in df.columns:
                continue
            all_times.extend(df["time_seconds"].values)
        except Exception:
            continue

    if len(all_times) == 0:
        return None

    return np.array(all_times)


# ----------------------------
# STATUS REPORT
# ----------------------------
def print_experiment_status():
    print("\n=== EXPERIMENT STATUS REPORT ===")

    for exp in EXPERIMENTS:
        path = RESULTS_DIR / exp

        if not path.exists():
            print(f"{exp:<18} [MISS] MISSING (no folder)")
            continue

        files = list(path.glob("*.csv"))

        if len(files) == 0:
            print(f"{exp:<18} [EMPTY] EMPTY (no CSV files)")
            continue

        total_rows = 0
        valid_files = 0

        for f in files:
            try:
                df = pd.read_csv(f)
                if "time_seconds" in df.columns:
                    total_rows += len(df)
                    valid_files += 1
            except Exception:
                continue

        if total_rows == 0:
            print(f"{exp:<18} INVALID (no usable data)")
        else:
            print(f"{exp:<18} [OK] FOUND ({total_rows} samples in {valid_files} files)")


# ----------------------------
# SUMMARY TABLE
# ----------------------------
def print_summary(data_dict):
    print("\n=== SUMMARY TABLE ===")
    print(f"{'Experiment':<18} {'Mean':<12} {'Std':<12} {'Min':<12} {'Max':<12}")

    for name, data in data_dict.items():
        print(f"{name:<18} "
              f"{np.mean(data):<12.6f} "
              f"{np.std(data):<12.6f} "
              f"{np.min(data):<12.6f} "
              f"{np.max(data):<12.6f}")


# ----------------------------
# HISTOGRAM
# ----------------------------
def plot_histograms(data_dict):
    if len(data_dict) == 0:
        print("[WARN] No data for histogram plot")
        return

    for name, data in data_dict.items():
        plt.figure()
        plt.hist(data, bins=50)
        plt.title(f"{name} Runtime Distribution")
        plt.xlabel("Time (seconds)")
        plt.ylabel("Frequency")

        out = PLOTS_DIR / name / "hist.png"
        plt.savefig(out)
        plt.close()

        # ----------------------------
        # PROVENANCE: RECORD PLOT
        # Log this file in the plots table linked to its
        # experiment so it can be traced from any run query.
        # ----------------------------
        try:
            db_manager.insert_plot(
                experiment_name=name,
                plot_type="histogram",
                file_path=str(out),
                source_script="compare.py"
            )
        except Exception as e:
            print(f"[WARN] Could not record plot provenance: {e}")

        print(f"[SAVED] {out}")

    # comparison plot — experiment_name is None because it
    # aggregates across all experiments rather than one
    plt.figure()
    for name, data in data_dict.items():
        plt.hist(data, bins=50, alpha=0.5, label=name)

    plt.legend()
    plt.title("Runtime Distribution Comparison")

    out = COMPARISON_DIR / "comparison_hist.png"
    plt.savefig(out)
    plt.close()

    try:
        db_manager.insert_plot(
            experiment_name=None,
            plot_type="comparison_histogram",
            file_path=str(out),
            source_script="compare.py"
        )
    except Exception as e:
        print(f"[WARN] Could not record plot provenance: {e}")

    print(f"[SAVED] {out}")


# ----------------------------
# BOXPLOT
# ----------------------------
def plot_boxplot(data_dict):
    if len(data_dict) == 0:
        print("[WARN] No data for boxplot")
        return

    for name, data in data_dict.items():
        plt.figure()
        plt.boxplot(data)
        plt.title(f"{name} Variability")
        plt.ylabel("Time (seconds)")

        out = PLOTS_DIR / name / "box.png"
        plt.savefig(out)
        plt.close()

        try:
            db_manager.insert_plot(
                experiment_name=name,
                plot_type="boxplot",
                file_path=str(out),
                source_script="compare.py"
            )
        except Exception as e:
            print(f"[WARN] Could not record plot provenance: {e}")

        print(f"[SAVED] {out}")

    # comparison boxplot
    plt.figure()

    labels = list(data_dict.keys())
    values = [data_dict[k] for k in labels]

    plt.boxplot(values, tick_labels=labels)
    plt.title("Runtime Variability Comparison")

    out = COMPARISON_DIR / "comparison_box.png"
    plt.savefig(out)
    plt.close()

    try:
        db_manager.insert_plot(
            experiment_name=None,
            plot_type="comparison_boxplot",
            file_path=str(out),
            source_script="compare.py"
        )
    except Exception as e:
        print(f"[WARN] Could not record plot provenance: {e}")

    print(f"[SAVED] {out}")


# ----------------------------
# MAIN
# ----------------------------
def main():
    print_experiment_status()

    print("\n=== Loading Experiments ===")

    data = {}

    for exp in EXPERIMENTS:
        result = load_experiment(exp)
        if result is not None:
            data[exp] = result
        else:
            print(f"[INFO] Skipping '{exp}' (no usable data)")

    if len(data) == 0:
        print("\n[ERROR] No valid experiment data found.")
        return

    print_summary(data)
    plot_histograms(data)
    plot_boxplot(data)

    print("\n=== DONE ===")
    print(f"Plots saved in: {PLOTS_DIR}")


if __name__ == "__main__":
    main()