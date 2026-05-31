# Runtime Experiment Pipeline – Project Overview

## 1. Introduction

This project is a cross-platform experimental computing framework for benchmarking CPU runtime behavior, analyzing jitter, and producing reproducible research artifacts. It integrates experiment execution, statistical analysis, database storage, visualization, and reproducibility tooling into a single automated pipeline.

---

## 2. System Architecture Overview

The system is organized as a multi-stage pipeline orchestrated by `batch_run.py`:

```text
(optional cleanup)
→ experiment execution
→ statistical analysis
→ database import
→ statistical hypothesis testing
→ anomaly detection
→ visualization generation
→ snapshot creation
→ dashboard
```

Each stage is modular and can be run independently.

---

## 3. Core Components

### 3.1 Experiment Engine

**File:** `BaselineRuntime_JitterMeasurement.py`

This module generates synthetic CPU workloads and measures runtime variability.

#### Features:

* Configurable number of runs
* Optional stress mode (increased workload size)
* Optional CPU pinning (best-effort, Linux only)
* High-resolution timing using `time.perf_counter()`
* Outputs:

  * CSV timing data
  * JSON metadata
  * Summary statistics (mean, std, percentiles)

#### Output Structure:

```text
results/<experiment_name>/<timestamp>.csv
results/<experiment_name>/<timestamp>_meta.json
```

---

### 3.2 Experiment Orchestrator

**File:** `batch_run.py`

This is the main control system that executes the full pipeline.

#### Responsibilities:

* Docker detection — skips venv bootstrap when running inside a container
* Virtual environment bootstrapping for native runs
* Dependency installation
* Cross-platform execution control
* Experiment registry loading from SQLite
* Pipeline stage orchestration

#### Pipeline Stages:

1. Optional cleanup
2. Load experiments from registry
3. Run experiments
4. Run analysis (`compare.py`)
5. Import into SQLite (`db_manager.py`)
6. Statistical hypothesis testing (`stats.py`)
7. Anomaly detection (`anomaly.py`)
8. Generate figures (`paper_figures.py`)
9. Create reproducibility snapshot (`snapshot.py`)
10. Launch dashboard

---

### 3.3 Analysis System

**File:** `compare.py`

This module performs file-based statistical analysis.

#### Features:

* Loads CSV outputs from experiments
* Computes mean, standard deviation, min/max
* Generates visualizations: histograms, boxplots, comparison plots

#### Output:

* `plots/` directory with experiment-specific figures

---

### 3.4 Database System

**File:** `db_manager.py`

This module provides persistent storage using SQLite.

#### Database Tables:

* **runs** — experiment metadata and system information
* **measurements** — per-run timing samples
* **experiment_registry** — source of truth for experiment definitions
* **snapshots** — provenance records
* **plots** — file path records for every generated figure
* **statistical_tests** — pairwise hypothesis test results
* **anomaly_flags** — Isolation Forest results per run

#### Features:

* CSV ingestion into structured DB
* Duplicate-safe imports via `(experiment_name, timestamp)` unique key
* Experiment registry with enable/disable support
* LaTeX export generation

#### LaTeX Output:

```
paper_figures/results_table.tex
```

---

### 3.5 Statistical Testing

**File:** `stats.py`

Runs pairwise hypothesis tests on every combination of experiments.

#### Methods:

* **Welch's t-test** — parametric test for difference in means, handles unequal variance
* **Mann-Whitney U test** — non-parametric test, no distribution assumption
* **Cohen's d** — effect size (practical magnitude of difference)
* **Bootstrap 95% confidence intervals** — robust CIs for non-normal distributions

Significance requires p < 0.05 on both tests for a conservative claim.

Results saved to `statistical_tests` table and exported as LaTeX.

---

### 3.6 Anomaly Detection

**File:** `anomaly.py`

Uses machine learning to flag runs that behave differently from historical patterns.

#### Approach:

* **Feature engineering** — each run is summarised as a 7D vector: mean, std, min, max, P95, P99, IQR
* **Isolation Forest** — unsupervised ML algorithm, no labelled data required
* **Z-score secondary signal** — high-confidence flags require both methods to agree
* **Contamination parameter** — user-configurable fraction of expected anomalies

Results saved to `anomaly_flags` table and displayed on the dashboard.

---

### 3.7 Snapshot System

**File:** `snapshot.py`

This module captures a full reproducibility snapshot of the experiment environment.

#### Captured Data:

* Git commit hash
* Python environment (`pip freeze` via `sys.executable`)
* Full `results/` directory
* Full `plots/` directory
* Database summary
* SHA-256 integrity hash of the entire snapshot

#### Output Structure:

```
snapshots/pipeline_YYYYMMDD_HHMMSS/
```

---

### 3.8 Cleanup System

**File:** `cleanup_files.py`

This module removes generated artifacts to reset the workspace.

#### Supported Deletions:

* `.csv`, `.json`, `.png`, `.tex` files
* SQLite database (`jitter.db`)
* Snapshots directory

#### Modes:

* Interactive mode (y/n prompts)
* CLI mode (flags for automation)
* Dry-run mode (safe preview)

---

## 4. Cross-Platform Compatibility

### Supported Systems:

#### macOS

* Fully supported
* CPU pinning disabled gracefully
* Venv created automatically on first native run

#### Linux

* Fully supported
* CPU affinity enabled via `os.sched_setaffinity`
* Venv created automatically on first native run

#### Windows

* Fully supported
* CPU pinning gracefully skipped
* Venv created automatically on first native run
* Dashboard accessible at `http://localhost:8501`

### Notes on CPU Pinning

CPU pinning (`--cpu` flag) uses `os.sched_setaffinity` which is only available on Linux. On macOS and Windows the flag is accepted but a warning is printed and pinning is skipped. Use the `cpu_pipeline` Docker service for true CPU affinity experiments on any host OS.

---

## 5. Reproducibility Features

The system ensures reproducibility via:

* Timestamped outputs
* Snapshot system (code + environment capture)
* Structured database logging with provenance linking
* Deterministic experiment naming
* Full artifact archiving
* Docker support for fully reproducible containerized execution
* `requirements-locked.txt` for guaranteed identical Docker builds

---

## 6. Error Handling Strategy

### Current Approach:

* Subprocess calls use `check=True`
* Pipeline aborts on critical failures
* Stats and anomaly steps are non-fatal — pipeline continues if they fail
* Graceful degradation for OS-specific features

### Limitations:

* Minimal retry logic
* No partial recovery system
* No structured error logging layer

---

## 7. Current System Limitations

### 7.1 No Real-Time Streaming

Dashboard reads from SQLite which is only updated when the pipeline completes. A truly real-time system would stream measurements via WebSocket.

### 7.2 No Database Migration System

Schema changes require manual handling of existing data. A migration tool like Alembic would make schema evolution safe.

### 7.3 Scale

Full directory scans on every import work fine for hundreds of runs but would become slow at thousands. Incremental imports would be needed at scale.

### 7.4 CPU Pinning

Only available on Linux natively. Use the `cpu_pipeline` Docker service for CPU affinity on macOS or Windows.

---

## 8. System Strengths

* Fully automated pipeline — single command runs everything
* Dual storage system (files + database)
* Full provenance chain — every result traceable to git commit, package versions, and system state
* Cross-platform on macOS, Linux, and Windows natively and via Docker
* Statistical rigor — dual hypothesis testing with effect size
* ML anomaly detection — unsupervised, no labelled data required
* Research-ready outputs — 300 DPI figures and LaTeX tables
* Modular architecture — every stage can be run independently

---

## 9. Future Improvements

### 9.1 Structured Error Logging

* Centralized logging system
* Failure tracking per pipeline stage

### 9.2 Extended Experiment Types

* Multi-threaded workloads (GIL contention effects)
* Memory-pressure experiments
* Network I/O jitter measurement
* GPU workload timing for AI inference latency

### 9.3 Cloud Deployment

Running experiments across multiple machines and cloud instance types would allow systematic comparison of how hardware affects runtime predictability.

### 9.4 Time Series Analysis

Formal autocorrelation and drift detection on the historical trend data.

---

## 10. Summary

This project implements a full experimental computing pipeline for runtime jitter analysis. It integrates execution, analysis, persistence, statistical testing, ML anomaly detection, visualization, cleanup, and reproducibility into a unified system that operates consistently across macOS, Linux, and Windows, with Docker support for fully containerized execution.

---

# ⚡ Runtime Jitter Monitor

An end-to-end system for measuring, storing, analyzing, and visualizing
runtime jitter in Python workloads under varying system conditions.
Built as both a research tool and a practical demonstration of
systems-level performance monitoring.

---

## What is Runtime Jitter?

Runtime jitter refers to the variation in execution time of a repeated
computational task. Even when running the same code repeatedly, execution
times fluctuate due to OS scheduling, CPU cache behavior, memory pressure,
and background system activity. Understanding and quantifying this
variation is critical in high-performance computing, real-time systems,
and AI inference infrastructure.

---

## What This Project Does

This system runs controlled experiments measuring how long a fixed
workload takes to execute across hundreds of iterations, under three
conditions:

- **Baseline** — normal execution, no constraints
- **Stress Test** — heavier workload simulating system load
- **CPU Pinned** — execution locked to a single CPU core (Linux only)

It stores all results in a structured SQLite database, runs statistical
hypothesis tests and ML anomaly detection, generates publication-quality
figures, exports LaTeX tables, takes reproducible snapshots of every run,
and displays everything on a live auto-refreshing dashboard.

---

## Project Structure

```
runtime-draft/
├── Dockerfile                                # Linux container image definition
├── docker-compose.yml                        # Docker service definitions
├── .dockerignore                             # files excluded from Docker image
├── .gitattributes                            # enforces Unix line endings
├── requirements.txt                          # unpinned dependencies for native runs
├── requirements-locked.txt                   # pinned Linux versions for Docker builds
├── scripts/
│   ├── BaselineRuntime_JitterMeasurement.py  # core measurement engine
│   ├── batch_run.py                          # master pipeline orchestrator
│   ├── compare.py                            # analysis and plot generation
│   ├── stats.py                              # statistical hypothesis testing
│   ├── anomaly.py                            # ML anomaly detection
│   ├── paper_figures.py                      # publication-quality figures
│   ├── cleanup_files.py                      # interactive artifact cleanup
│   ├── db_manager.py                         # SQLite database management
│   ├── snapshot.py                           # reproducibility snapshots
│   └── dashboard.py                          # live Streamlit dashboard
├── results/                                  # raw CSV and JSON outputs
├── plots/                                    # generated plot images
├── paper_figures/                            # publication figures + LaTeX
├── databases/                                # SQLite database
├── snapshots/                                # reproducibility snapshots
├── dashboard/                                # dashboard assets
└── tests/                                    # unit tests
    ├── test_db_manager.py
    ├── test_cleanup_files.py
    └── test_measurement.py
```

---

## Quickstart

### Requirements

- Python 3.11+ **or** Docker

### Option 1: Run with Docker (recommended — works on any platform)

Docker runs a Linux container so no Python installation or virtual environment
is needed on your machine. Dependencies are installed inside the container
at build time using `requirements-locked.txt` for guaranteed reproducible builds.

First, build the image:
```bash
docker compose build
```

Then choose what to run:

```bash
# Run the full pipeline (interactive)
docker compose --profile pipeline run --service-ports pipeline

# Run with true CPU pinning (Linux container — works on macOS, Windows, and Linux)
docker compose --profile cpu run --service-ports cpu_pipeline

# Launch the dashboard only
docker compose up dashboard
```

Then open `http://localhost:8501` in your browser.

> **Note:** `--service-ports` is required when using `docker compose run`
> to bind port 8501 so the dashboard is accessible in your browser.

Results, plots, and databases are saved back to your local machine
automatically via mounted volumes — you keep all your data even after
the container stops.

### Option 2: Run natively

No manual setup needed — `batch_run.py` automatically creates a virtual
environment and installs dependencies on first run. Just make sure
Python 3.11+ is installed, then:

macOS/Linux:
```bash
python scripts/batch_run.py
```

Windows:
```cmd
python scripts\batch_run.py
```

On first run this will automatically:

1. Create and configure a virtual environment
2. Install all dependencies
3. Load experiments from the registry
4. Run all three experiments
5. Generate analysis plots
6. Import results into SQLite
7. Run statistical hypothesis tests
8. Run ML anomaly detection
9. Generate publication figures
10. Take a reproducibility snapshot
11. Ask if you want to launch the dashboard

On subsequent runs the venv is already in place so setup is skipped.

### Run with cleanup first

```bash
python scripts/batch_run.py --clean
```

### Run the dashboard standalone

```bash
python -m streamlit run scripts/dashboard.py
```

Then open `http://localhost:8501` in your browser.

### Run the tests

```bash
pytest tests/ -v
```

---

## Features

### Measurement Engine
- High-precision timing using `time.perf_counter()`
- Configurable warmup runs to eliminate cold-start bias
- Three experiment modes: baseline, stress, CPU-pinned
- Automatic metadata capture: OS, CPU, Python version, timestamp
- Cross-platform: macOS, Linux, Windows

### Data Pipeline
- Raw results saved as CSV with matching JSON metadata per run
- SQLite database with normalized schema
- Duplicate-safe imports — re-running the pipeline never double-inserts data
- LaTeX table export for direct use in academic papers

### Statistical Analysis
- Welch's t-test and Mann-Whitney U test for pairwise significance testing
- Cohen's d effect size — separates statistical from practical significance
- Bootstrap 95% confidence intervals — robust for non-normal distributions
- Significance requires p < 0.05 on both tests for a conservative claim

### ML Anomaly Detection
- Isolation Forest — unsupervised, no labelled data required
- 7-dimensional feature vectors per run: mean, std, min, max, P95, P99, IQR
- Z-score secondary signal — high-confidence flags require both methods
- User-configurable contamination parameter
- Results stored in database and displayed on dashboard

### Analysis and Visualization
- Per-experiment histograms and boxplots
- Cross-experiment comparison plots
- Publication-quality figures at 300 DPI
- Tail latency analysis across P50, P95, and P99 percentiles

### Live Dashboard
- Real-time auto-refreshing Streamlit dashboard
- Dark mode with per-experiment color coding
- Summary statistics cards per experiment
- Interactive runtime distribution histogram
- Variability boxplot comparison
- Tail latency chart
- Historical mean jitter trend over time
- Statistical test results panel
- ML anomaly detection panel with flagged runs and confidence levels
- Sidebar controls for refresh interval, experiment filter, and run limit

### Reproducibility
- Timestamped snapshots capturing git commit, pip freeze, all results,
  all plots, LaTeX tables, and a database summary
- SHA-256 integrity hash of each snapshot
- Provenance linking — every run linked to its snapshot in the database
- `requirements-locked.txt` for guaranteed identical Docker builds
- Docker support for fully reproducible containerized execution

### Cleanup
- Interactive cleanup tool with dry-run mode by default
- Separate controls for CSVs, JSONs, PNGs, TEX files, database, snapshots
- Protected directories never touched: .venv, .git, __pycache__, dashboard
- Full deletion log saved after every cleanup run

### Testing
- Unit tests covering database operations, duplicate detection,
  file cleanup logic, and statistical computations
- Uses temporary directories so tests never touch real project data
- Run with `pytest tests/ -v`

---

## Experiment Results

Running on Apple M1 (macOS), 200 iterations per experiment:

| Experiment   | Mean (s) | Std Dev (s) | P95 (s) | P99 (s) |
|--------------|----------|-------------|---------|---------|
| baseline     | 0.0067   | 0.0009      | 0.0071  | 0.0094  |
| stress_test  | 0.0264   | 0.0003      | 0.0267  | 0.0274  |
| cpu_pinned_0 | 0.0069   | 0.0014      | 0.0085  | 0.0128  |

Note: CPU pinning is not supported on macOS or Windows. Results for
`cpu_pinned_0` on these platforms are equivalent to baseline. Run on
Linux or inside a Linux Docker container for true CPU affinity results.

---

## Strengths

- **Complete system** — not just a script but a full pipeline with
  orchestration, storage, statistical testing, ML anomaly detection,
  visualization, and reproducibility built in
- **Statistical rigor** — dual hypothesis testing with effect size
  separates meaningful differences from statistical noise
- **ML anomaly detection** — unsupervised run-level detection using
  Isolation Forest with a Z-score secondary signal
- **Production habits** — virtual environment management, duplicate
  detection, logging, error handling, and cross-platform compatibility
- **Research-ready outputs** — 300 DPI figures and LaTeX tables ready
  for direct inclusion in academic papers
- **Reproducible by design** — every run is snapshotted with enough
  information to recreate results exactly
- **Docker support** — fully containerized execution with locked
  dependencies for maximum portability and reproducibility

---

## Known Limitations and Areas for Improvement

### True Real-Time Dashboard
The dashboard reads from SQLite which is only updated when the pipeline
completes. A truly real-time system would stream measurements directly
to the dashboard as each experiment executes, using a message queue or
WebSocket connection.

### CPU Pinning on macOS and Windows
macOS does not expose `sched_setaffinity` and Windows does not support
it through Python's `os` module. True CPU affinity experiments require
Linux. The `cpu_pipeline` Docker service runs a privileged Linux
container with `cpuset: "0"`, so CPU pinning works correctly when using
Docker on any host OS — including macOS and Windows.

### Database Migration Strategy
The current schema has no migration system. Adding new columns in future
versions requires manually handling existing data. A migration tool like
Alembic would make schema evolution safe and reversible.

### Scale
The current import system scans the entire results folder on every run.
This works fine for hundreds of runs but would become slow at thousands.
Indexing and incremental imports would be needed at scale.

---

## Future Directions

### Extended Experiment Types
- Multi-threaded workloads to study GIL contention effects on jitter
- Memory-pressure experiments
- Network I/O jitter measurement
- GPU workload timing for AI inference latency analysis

### Cloud Deployment
Running experiments across multiple machines and cloud instance types
would allow systematic comparison of how hardware affects runtime
predictability — directly relevant to AI server infrastructure work.

### Time Series Analysis
Formal autocorrelation and drift detection on the historical trend data
to identify long-term performance degradation.

---

## Requirements

**Native runs** (`requirements.txt` — unpinned, resolves for your platform):
```
streamlit
plotly
pandas
numpy
matplotlib
gitpython
pytest
pyarrow
pydeck
requests
scikit-learn
scipy
joblib
```

**Docker builds** (`requirements-locked.txt` — pinned Linux versions for
guaranteed reproducible container builds).

Install for native use:
```bash
pip install -r requirements.txt
```

---

## Authors

Built as an independent research and portfolio project exploring
runtime performance monitoring and system jitter characterization.

---

## License

MIT
