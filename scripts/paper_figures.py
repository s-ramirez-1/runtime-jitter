# paper_figures.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import sys

# ----------------------------
# CONFIG
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"
OUTPUT_DIR = PROJECT_ROOT / "paper_figures"

# ----------------------------
# LOAD EXPERIMENTS FROM REGISTRY
# Replaces the hardcoded EXPERIMENTS list.
# Falls back gracefully if DB isn't available yet.
# ----------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import db_manager
    db_manager.create_tables()
    db_manager.seed_default_experiments()
    EXPERIMENTS = [exp["name"] for exp in db_manager.get_experiments()]
except Exception as e:
    print(f"[WARN] Could not load registry, falling back to defaults: {e}")
    EXPERIMENTS = ["baseline", "stress_test", "cpu_pinned_0"]

STYLE = {
    "baseline": "black",
    "stress_test": "red",
    "cpu_pinned_0": "blue",
}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------
# LOAD DATA
# ----------------------------
def load_experiment(exp):
    path = RESULTS_DIR / exp

    if not path.exists():
        print(f"[WARN] {exp}: folder missing")
        return None

    files = list(path.glob("*.csv"))

    if not files:
        print(f"[WARN] {exp}: no CSV files found")
        return None

    values = []

    for f in files:
        try:
            df = pd.read_csv(f)

            if "time_seconds" not in df.columns:
                print(f"[WARN] {exp}: invalid file format {f.name}")
                continue

            values.extend(df["time_seconds"].values)

        except Exception as e:
            print(f"[WARN] {exp}: failed to read {f.name} -> {e}")

    if len(values) == 0:
        print(f"[WARN] {exp}: no usable data")
        return None

    return np.array(values)


# ----------------------------
# FIGURE 1: DISTRIBUTION
# ----------------------------
def fig_distribution(data):
    plt.figure()

    for name, values in data.items():
        if values is None or len(values) == 0:
            print(f"[WARN] skipping {name} in Figure 1 (no data)")
            continue

        plt.hist(values, bins=60, alpha=0.4,
                 label=name,
                 color=STYLE.get(name, "gray"))

    if len(data) == 0:
        print("[ERROR] No data for distribution figure")
        return

    plt.title("Runtime Distribution Under System Conditions")
    plt.xlabel("Execution Time (seconds)")
    plt.ylabel("Frequency")
    plt.legend()

    out = OUTPUT_DIR / "figure_1_distribution.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()

    # ----------------------------
    # PROVENANCE: RECORD FIGURE
    # experiment_name is None because this figure aggregates
    # all experiments rather than belonging to one.
    # ----------------------------
    try:
        db_manager.insert_plot(
            experiment_name=None,
            plot_type="figure_distribution",
            file_path=str(out),
            source_script="paper_figures.py"
        )
    except Exception as e:
        print(f"[WARN] Could not record plot provenance: {e}")

    print(f"[SAVED] {out}")


# ----------------------------
# FIGURE 2: VARIABILITY
# ----------------------------
def fig_variability(data):
    valid = {k: v for k, v in data.items() if v is not None and len(v) > 0}

    if not valid:
        print("[ERROR] No data for variability figure")
        return

    names = list(valid.keys())
    stds = [np.std(valid[n]) for n in names]

    plt.figure()

    plt.bar(names, stds, color=[STYLE.get(n, "gray") for n in names])

    plt.title("Runtime Variability (Standard Deviation)")
    plt.ylabel("Std Dev (seconds)")

    out = OUTPUT_DIR / "figure_2_variability.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()

    try:
        db_manager.insert_plot(
            experiment_name=None,
            plot_type="figure_variability",
            file_path=str(out),
            source_script="paper_figures.py"
        )
    except Exception as e:
        print(f"[WARN] Could not record plot provenance: {e}")

    print(f"[SAVED] {out}")


# ----------------------------
# FIGURE 3: TAIL LATENCY
# ----------------------------
def fig_tail_latency(data):
    valid = {k: v for k, v in data.items() if v is not None and len(v) > 0}

    if not valid:
        print("[ERROR] No data for tail latency figure")
        return

    plt.figure()

    for name, values in valid.items():
        values = np.sort(values)

        p50 = np.percentile(values, 50)
        p95 = np.percentile(values, 95)
        p99 = np.percentile(values, 99)

        plt.plot(
            ["P50", "P95", "P99"],
            [p50, p95, p99],
            marker="o",
            label=name,
            color=STYLE.get(name, "gray")
        )

    plt.title("Tail Latency Comparison")
    plt.ylabel("Time (seconds)")
    plt.legend()

    out = OUTPUT_DIR / "figure_3_tail_latency.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()

    try:
        db_manager.insert_plot(
            experiment_name=None,
            plot_type="figure_tail_latency",
            file_path=str(out),
            source_script="paper_figures.py"
        )
    except Exception as e:
        print(f"[WARN] Could not record plot provenance: {e}")

    print(f"[SAVED] {out}")


# ----------------------------
# MAIN
# ----------------------------
def main():
    print("\n=== LOADING DATA FOR PAPER FIGURES ===")

    data = {}

    for exp in EXPERIMENTS:
        values = load_experiment(exp)

        if values is None:
            print(f"[INFO] {exp}: not included in figures (no data)")
        else:
            print(f"[OK] {exp}: loaded ({len(values)} samples)")
            data[exp] = values

    if not data:
        print("\n[ERROR] No valid data available for any figure.")
        return

    fig_distribution(data)
    fig_variability(data)
    fig_tail_latency(data)

    print("\n=== DONE ===")
    print(f"Paper figures saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()