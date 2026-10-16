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
    # --- GPU additions ---
    parser.add_argument("--workload", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--gpu-sample-interval", type=float, default=0.25,
                        help="GPU telemetry polling interval in seconds (0 disables sampling)")
    args = parser.parse_args()

    print(f"[RUN] Experiment: {args.name}")
    print(f"[INFO] Workload: {args.workload}")
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
    gpu_env = None
    gpu_samples = []
    gpu_summary = None

    if args.workload == "gpu":
        # imported lazily so CPU-only machines never need torch
        import gpu_workload
        import gpu_sampler

        gpu_env = gpu_workload.environment_info()
        if args.gpu_sample_interval > 0:
            with gpu_sampler.GPUSampler(args.gpu_sample_interval) as sampler:
                times = gpu_workload.run_experiment(args.runs, stress=args.stress)
            gpu_samples = sampler.samples
            gpu_summary = gpu_sampler.summarize(gpu_samples) if gpu_samples else None
        else:
            times = gpu_workload.run_experiment(args.runs, stress=args.stress)
    else:
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
    # GPU samples go in a JSON sidecar, not a CSV, so scripts that glob results/*.csv
    # (db_manager.import_all, and probably compare.py) never mistake it for a run file.
    gpu_path = out_dir / f"{args.name}_{timestamp}_gpu.json"

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
        "num_runs": args.runs,
        # --- GPU additions ---
        "workload": args.workload,
        "gpu": gpu_env,
        "gpu_summary": gpu_summary,
    }

    # ----------------------------
    # SAVE OUTPUTS
    # ----------------------------
    save_csv(times, csv_path)
    save_metadata(metadata, meta_path)
    if gpu_samples:
        with open(gpu_path, "w") as f:
            json.dump({"interval_s": args.gpu_sample_interval, "samples": gpu_samples}, f)

    # ----------------------------
    # RESULTS PRINT (UPGRADED)
    # ----------------------------
    stats = compute_stats(times)

    print("\n=== RESULTS ===")
    for k in ["mean", "std", "p50", "p95", "p99", "min", "max"]:
        print(f"{k:<12}: {stats[k]:.6f}")

    if gpu_summary:
        print("\n=== GPU TELEMETRY ===")
        for k, v in gpu_summary.items():
            print(f"{k:<16}: {v:.2f}" if isinstance(v, float) else f"{k:<16}: {v}")

    print("\nSaved CSV :", csv_path)
    print("Saved META:", meta_path)
    if gpu_samples:
        print("Saved GPU :", gpu_path)

# ----------------------------
# ENTRY POINT
# ----------------------------
if __name__ == "__main__":
    main()
