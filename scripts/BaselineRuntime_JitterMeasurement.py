# BaselineRuntime_JitterMeasurement.py
import time
import csv
import os
import platform
import argparse
import json
from datetime import datetime
import numpy as np
from pathlib import Path

# ----------------------------
# CONFIG
# ----------------------------
DEFAULT_RUNS = 200
WARMUP_RUNS = 10

# ----------------------------
# WORKLOAD
# ----------------------------
def workload(stress=False):
    total = 0
    n = 200_000 if not stress else 800_000

    for i in range(n):
        total += (i * i) % 97

    return total

# ----------------------------
# MEASURE
# ----------------------------
def run_experiment(n_runs, stress=False):
    times = []

    # warmup
    for _ in range(WARMUP_RUNS):
        workload(stress)

    # timed runs
    for _ in range(n_runs):
        start = time.perf_counter()
        workload(stress)
        end = time.perf_counter()
        times.append(end - start)

    return np.array(times)

# ----------------------------
# SAVE CSV
# ----------------------------
def save_csv(times, filename):
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "time_seconds"])
        for i, t in enumerate(times):
            writer.writerow([i, t])

# ----------------------------
# SAVE METADATA
# ----------------------------
def save_metadata(meta, filename):
    with open(filename, "w") as f:
        json.dump(meta, f, indent=2)

# ----------------------------
# STATS (NEW CLEAN BLOCK)
# ----------------------------
def compute_stats(times):
    return {
        "mean": np.mean(times),
        "std": np.std(times),
        "min": np.min(times),
        "max": np.max(times),
        "p50": np.percentile(times, 50),
        "p95": np.percentile(times, 95),
        "p99": np.percentile(times, 99),
    }

# ----------------------------
# MAIN
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--stress", action="store_true")
    parser.add_argument("--cpu", type=int, default=None)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    args = parser.parse_args()

    print(f"[RUN] Experiment: {args.name}")
    print(f"[INFO] Stress mode: {args.stress}")

    # ----------------------------
    # CPU PINNING (best effort)
    # ----------------------------
    if args.cpu is not None:
        try:
            if hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(0, {args.cpu})
                print(f"[INFO] Pinned to CPU {args.cpu}")
            else:
                print("[WARN] CPU pinning not supported on this OS")
        except Exception as e:
            print(f"[WARN] CPU pinning failed: {e}")

    # ----------------------------
    # RUN EXPERIMENT
    # ----------------------------
    times = run_experiment(args.runs, stress=args.stress)

    # ----------------------------
    # PATH SETUP (UNCHANGED)
    # ----------------------------
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    out_dir = PROJECT_ROOT / "results" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = out_dir / f"{args.name}_{timestamp}.csv"
    meta_path = out_dir / f"{args.name}_{timestamp}_meta.json"

    # ----------------------------
    # METADATA
    # ----------------------------
    metadata = {
        "experiment": args.name,
        "timestamp": datetime.now().isoformat(),
        "os": platform.system(),
        "os_release": platform.release(),
        "cpu": platform.processor(),
        "python_version": platform.python_version(),
        "args": vars(args),
        "num_runs": args.runs
    }

    # ----------------------------
    # SAVE OUTPUTS
    # ----------------------------
    save_csv(times, csv_path)
    save_metadata(metadata, meta_path)

    # ----------------------------
    # RESULTS PRINT (UPGRADED)
    # ----------------------------
    stats = compute_stats(times)

    print("\n=== RESULTS ===")
    for k in ["mean", "std", "p50", "p95", "p99", "min", "max"]:
        print(f"{k:<12}: {stats[k]:.6f}")

    print("\nSaved CSV :", csv_path)
    print("Saved META:", meta_path)

# ----------------------------
# ENTRY POINT
# ----------------------------
if __name__ == "__main__":
    main()

# WAYS TO RUN ON LINUX
"""
python scripts/BaselineRuntime_JitterMeasurement.py --name baseline
python scripts/BaselineRuntime_JitterMeasurement.py --name cpu_pinned_0 --cpu 0
python scripts/BaselineRuntime_JitterMeasurement.py --name cpu_pinned_0_1 --cpu 0,1 # this is the same as above
python scripts/BaselineRuntime_JitterMeasurement.py --name stress_test --stress
python scripts/BaselineRuntime_JitterMeasurement.py --name pinned_stress --cpu 0 --stress
"""

# WAYS TO RUN ON macOS
"""
python scripts/BaselineRuntime_JitterMeasurement.py --name baseline
python scripts/BaselineRuntime_JitterMeasurement.py --name stress_test --stress
"""