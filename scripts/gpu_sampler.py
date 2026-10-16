# gpu_sampler.py
"""Background GPU telemetry sampler.

Prefers NVML (pip install nvidia-ml-py) because it reads counters in-process.
Falls back to polling nvidia-smi, which spawns a subprocess per sample and can
itself add timing noise to a jitter measurement. Keep that in mind when
interpreting results, or run with --gpu-sample-interval 0 to disable sampling.
"""
import shutil
import subprocess
import threading
import time

SMI_QUERY = "index,utilization.gpu,memory.used,power.draw,temperature.gpu,clocks.sm"
SMI_CMD = ["nvidia-smi", f"--query-gpu={SMI_QUERY}", "--format=csv,noheader,nounits"]
FIELDS = ["util_pct", "mem_mib", "power_w", "temp_c", "sm_mhz"]


def _num(x):
    try:
        return float(x)
    except ValueError:
        return None  # nvidia-smi prints [N/A] for unsupported fields


def parse_smi_output(text, ts):
    rows = []
    for line in text.strip().splitlines():
        p = [s.strip() for s in line.split(",")]
        if len(p) != 6:
            continue
        rows.append({"ts": ts, "gpu_idx": int(p[0]), "util_pct": _num(p[1]), "mem_mib": _num(p[2]),
                     "power_w": _num(p[3]), "temp_c": _num(p[4]), "sm_mhz": _num(p[5])})
    return rows


def summarize(samples):
    """Mean and max of each field across all samples (None values ignored)."""
    out = {}
    for f in FIELDS:
        v = [s[f] for s in samples if s.get(f) is not None]
        if v:
            out[f"{f}_mean"] = sum(v) / len(v)
            out[f"{f}_max"] = max(v)
    out["n_samples"] = len(samples)
    return out


class GPUSampler:
    def __init__(self, interval_s=0.25):
        self.interval_s = interval_s
        self.samples = []
        self.backend = None
        self._stop = threading.Event()
        self._thread = None
        self._nvml = None
        self._handles = []

    def _init_backend(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
            self._handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(pynvml.nvmlDeviceGetCount())]
            self.backend = "nvml"
        except Exception:
            if shutil.which("nvidia-smi"):
                self.backend = "nvidia-smi"

    def _sample_nvml(self):
        n = self._nvml
        ts = time.time()
        rows = []
        for i, h in enumerate(self._handles):
            rows.append({
                "ts": ts, "gpu_idx": i,
                "util_pct": float(n.nvmlDeviceGetUtilizationRates(h).gpu),
                "mem_mib": n.nvmlDeviceGetMemoryInfo(h).used / 2**20,
                "power_w": n.nvmlDeviceGetPowerUsage(h) / 1000.0,
                "temp_c": float(n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU)),
                "sm_mhz": float(n.nvmlDeviceGetClockInfo(h, n.NVML_CLOCK_SM)),
            })
        return rows

    def _loop(self):
        while not self._stop.is_set():
            try:
                if self.backend == "nvml":
                    self.samples.extend(self._sample_nvml())
                else:
                    out = subprocess.run(SMI_CMD, capture_output=True, text=True, timeout=5, check=True).stdout
                    self.samples.extend(parse_smi_output(out, time.time()))
            except Exception:
                pass  # a failed poll should never kill a measurement run
            self._stop.wait(self.interval_s)

    def start(self):
        self._init_backend()
        if self.backend is None:
            print("[GPU] No NVML or nvidia-smi found; telemetry disabled")
            return self
        print(f"[GPU] Telemetry backend: {self.backend} (every {self.interval_s}s)")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_s + 6)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
