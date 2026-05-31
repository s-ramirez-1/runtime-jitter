# test_measurement.py
import pytest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from BaselineRuntime_JitterMeasurement import compute_stats, workload

# ----------------------------
# TESTS: COMPUTE STATS
# ----------------------------
def test_compute_stats_mean():
    times = np.array([0.001, 0.002, 0.003, 0.004, 0.005])
    stats = compute_stats(times)
    assert abs(stats["mean"] - 0.003) < 1e-9


def test_compute_stats_min_max():
    times = np.array([0.001, 0.002, 0.003, 0.004, 0.005])
    stats = compute_stats(times)
    assert abs(stats["min"] - 0.001) < 1e-9
    assert abs(stats["max"] - 0.005) < 1e-9


def test_compute_stats_std():
    times = np.array([1.0, 1.0, 1.0, 1.0])
    stats = compute_stats(times)
    assert abs(stats["std"] - 0.0) < 1e-9


def test_compute_stats_percentiles():
    times = np.array([float(i) for i in range(1, 101)])
    stats = compute_stats(times)
    assert abs(stats["p50"] - 50.5) < 0.1
    assert abs(stats["p95"] - 95.05) < 0.5
    assert abs(stats["p99"] - 99.01) < 0.5


def test_compute_stats_keys():
    times = np.array([0.001, 0.002, 0.003])
    stats = compute_stats(times)
    expected_keys = {"mean", "std", "min", "max", "p50", "p95", "p99"}
    assert set(stats.keys()) == expected_keys


def test_compute_stats_single_value():
    times = np.array([0.005])
    stats = compute_stats(times)
    assert abs(stats["mean"] - 0.005) < 1e-9
    assert abs(stats["min"] - 0.005) < 1e-9
    assert abs(stats["max"] - 0.005) < 1e-9


# ----------------------------
# TESTS: WORKLOAD
# ----------------------------
def test_workload_returns_value():
    result = workload(stress=False)
    assert isinstance(result, int)


def test_workload_stress_returns_value():
    result = workload(stress=True)
    assert isinstance(result, int)


def test_workload_deterministic():
    result1 = workload(stress=False)
    result2 = workload(stress=False)
    assert result1 == result2


def test_workload_stress_deterministic():
    result1 = workload(stress=True)
    result2 = workload(stress=True)
    assert result1 == result2
