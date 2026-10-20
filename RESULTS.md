# Results

Measured results and their discussion for the Runtime Jitter Monitor. The [README](README.md) describes how the system works; this file holds what it found.

Results below are from 2026-10-20, pipeline snapshot `dc094845a257` (snapshot id 10). All times are in milliseconds unless noted.

## Setup and data

All runs were on one Windows laptop under WSL2 (Linux), with an NVIDIA RTX 3050 Laptop GPU (4 GB, 35 W power cap). Each run times 200 repetitions of the workload.

- **CPU experiments** (`baseline`, `stress_test` at 4x workload, `cpu_pinned_0` pinned to core 0): 38 runs each, 7,600 timings each, accumulated over several pipeline invocations.
- **GPU experiments** (`gpu_baseline`, `gpu_stress` at 4x batch, `gpu_pinned_0` with the host process pinned to core 0): one 200-timing run each, plus a 3-timing smoke test for `gpu_baseline` and `gpu_stress`. The GPU workload is one ResNet-18 training step per timing (batch 16, or 64 in stress mode) on synthetic data, with GPU telemetry sampled through NVML every 0.25 s.

The transformer GPU workload (`gpu_tf_*` experiments) has not been run yet; results will be added here when it has.

## Results

**Most recent run of each experiment** (200 timings each):

| Experiment | Mean | Std | Std / mean | p99 | Max |
| --- | --- | --- | --- | --- | --- |
| baseline | 37.45 | 13.70 | 36.6% | 80.58 | 98.11 |
| stress_test | 120.55 | 37.67 | 31.2% | 239.89 | 266.82 |
| cpu_pinned_0 | 19.53 | 2.69 | 13.8% | 31.05 | 33.10 |
| gpu_baseline | 78.12 | 0.99 | 1.3% | 80.05 | 80.27 |
| gpu_stress | 281.28 | 1.59 | 0.6% | 284.69 | 285.58 |
| gpu_pinned_0 | 78.55 | 1.21 | 1.5% | 80.66 | 87.49 |

**Pairwise tests** from `stats.py`, pooling every imported timing. A pair counts as significant only if both the Welch and Mann-Whitney p-values are below 0.05.

| Comparison | Timings | Mean A → B (ms) | Welch t | Mann-Whitney p | Cohen's d | Significant |
| --- | --- | --- | --- | --- | --- | --- |
| baseline vs stress_test | 7,600 / 7,600 | 13.16 → 51.15 | −92.2 | <0.001 | −1.49 | Yes |
| baseline vs cpu_pinned_0 | 7,600 / 7,600 | 13.16 → 12.97 | 1.21 (p = 0.23) | <0.001 | 0.02 | No |
| stress_test vs cpu_pinned_0 | 7,600 / 7,600 | 51.15 → 12.97 | 92.9 | <0.001 | 1.51 | Yes |
| gpu_baseline vs gpu_stress | 203 / 203 | 78.06 → 281.05 | −1,073 | <0.001 | −106.5 | Yes |
| gpu_baseline vs gpu_pinned_0 | 203 / 200 | 78.06 → 78.55 | −4.22 (p = 0.00003) | 0.00006 | −0.42 | Yes |
| gpu_stress vs gpu_pinned_0 | 203 / 200 | 281.05 → 78.55 | 1,047.8 | <0.001 | 104.2 | Yes |

## Findings

1. **Runtime scales almost in proportion to the work.** CPU stress is 3.9x baseline (51.15 vs 13.16 ms pooled means) for 4x the workload. GPU stress is 3.6x (281.05 vs 78.06 ms) for a 4x batch, so the GPU handles the larger batch slightly more efficiently.
2. **CPU pinning reduces spread, not the mean.** The pooled means match (13.16 vs 12.97 ms, Welch p = 0.23, d = 0.02), but in the latest run pinning cut the standard deviation from 13.7 to 2.7 ms and p99/p50 from 2.5 to 1.6. Mann-Whitney still finds a difference between the two distributions, which fits a change in shape. Welch's test compares only means, so a variance test is needed to confirm this.
3. **On the CPU, run-to-run drift is larger than any condition effect.** Backing the earlier run out of the summary table gives baseline means of about 12 ms and 37 ms in two consecutive runs, stress_test about 46 ms and 121 ms, and cpu_pinned_0 about 12 ms and 20 ms. Background load on the laptop is the likely cause, but this has not been confirmed. It also means the narrow pooled 95% intervals (baseline: 12.94–13.37 ms) understate the real uncertainty.
4. **The GPU workload is far steadier than the CPU one.** Its standard deviation is 0.6–1.5% of the mean, against 14–37% for the CPU workload in the latest runs. In stress mode the GPU ran at its power limit: 34.0 W mean against a 35 W cap, 96% utilization, 55 °C, and an SM clock averaging 1,380 MHz against a 1,477 MHz peak.
5. **Pinning the host process to core 0 made the GPU workload slightly slower**, by about 0.4 ms (0.5%, d = −0.42, small), and the pinned run had one 87.5 ms spike. The difference is statistically significant, but it comes from one run per condition measured in a fixed order, with GPU temperature rising from 48.9 °C to 53.4 °C between baseline and pinned. It cannot be attributed to pinning.
6. **Anomaly detection** (Isolation Forest, contamination 0.05) flagged 2 of 38 runs in each CPU experiment, which the setting forces. Only two runs are high confidence, meaning the Z-score check agrees: stress_test run 84 (z = 3.04) and cpu_pinned_0 run 75 (z = 3.52). Baseline had none (highest z = 2.79). The GPU experiments were skipped because each has fewer than 3 runs.

## Limitations

- **One GPU run per condition.** There is no run-to-run view of the GPU workload, and anomaly detection cannot run on it (it needs at least 3 runs).
- **Smoke-test timings are mixed into the GPU data.** `gpu_baseline` and `gpu_stress` each include 3 timings from an earlier test taken with a cooler GPU. They set the reported minimums (74.0 and 264.1 ms) and inflate the pooled `gpu_stress` standard deviation to 2.46 ms, against 1.59 ms in the full run.
- **The 200 timings in a run are correlated, but the tests treat them as independent.** The p-values are therefore too small, and the Cohen's d values above 100 for the GPU comparisons mostly reflect one run's very low noise.
- **No multiple-comparison correction** across the six tests. At a Bonferroni threshold of 0.0083, the GPU pinning result still passes.
- **Fixed run order on a laptop.** Experiments ran in the same order each time, on a GPU with a 35 W power cap, under WSL2, so thermal drift and host effects cannot be separated from the conditions.
- **Snapshot provenance is only partly accurate.** Snapshot 10 was stamped onto all 119 runs, including 108 imported in earlier sessions, so it identifies the code state for the latest 11 runs only. The "0 / 119 linked" line in the database summary prints before the snapshot step runs.
- **Some printed summaries are stale or narrower than they look.** The database summary prints before the stats and anomaly steps, so its test results are from the previous pipeline run. The comparison summary table covers only the two most recent files per CPU experiment. The figures in this file come from the `stats.py` output and the per-run printouts.

## Next steps

1. Remove the two 3-timing smoke-test runs (run ids 113 and 116) and their result files, then re-run the stats.
2. Collect at least 10 GPU runs per condition by re-running the pipeline, so anomaly detection and run-level analysis work for the GPU.
3. Randomize or interleave the experiment order, and let the GPU cool between runs.
4. Add a variance test (Levene or Brown-Forsythe) for the pinning question, and compare per-run means, or use a block bootstrap, to account for correlated timings.
5. Apply a multiple-comparison correction to the pairwise tests.
6. Limit snapshot stamping to the runs imported in the current pipeline invocation, so provenance is accurate for every run.
7. Run the transformer GPU experiments and add their results to this file.

## Earlier results (Apple M1, macOS)

These numbers come from the original README, measured on an Apple M1 (macOS) with 200 iterations per experiment. They are on a different machine and workload size from the results above, so do not compare them directly.

| Experiment | Mean (s) | Std Dev (s) | P95 (s) | P99 (s) |
| --- | --- | --- | --- | --- |
| baseline | 0.0067 | 0.0009 | 0.0071 | 0.0094 |
| stress_test | 0.0264 | 0.0003 | 0.0267 | 0.0274 |
| cpu_pinned_0 | 0.0069 | 0.0014 | 0.0085 | 0.0128 |

CPU pinning is not supported on macOS or Windows, so `cpu_pinned_0` there is equivalent to baseline. Run on Linux, or inside a Linux Docker container, for true CPU affinity results.
