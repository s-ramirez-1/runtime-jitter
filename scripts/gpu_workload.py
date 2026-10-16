# gpu_workload.py
"""GPU workload for the jitter pipeline: one ResNet-18 training step per timed run.

Mirrors the CPU workload's structure (warmup, then N timed runs) so the output is a
plain array of per-run times that flows through the existing CSV -> DB -> stats path.
The batch lives on the GPU and is reused, so this isolates compute and scheduling
variability rather than input-pipeline variability. --stress uses a 4x batch size,
matching the CPU workload's 4x stress definition.
"""
import platform
import random
import subprocess
import time

import numpy as np

SEED = 1234
WARMUP_RUNS = 10
BATCH = 32
STRESS_BATCH = 128   # 4x
NUM_CLASSES = 10


def _require_torch():
    try:
        import torch
        import torchvision  # noqa: F401
        return torch
    except ImportError as e:
        raise SystemExit(f"[ERROR] GPU workload needs torch/torchvision ({e}). "
                         "Install requirements-gpu.txt or run inside the GPU image.")


def environment_info():
    """GPU/software environment for run metadata (stored in the *_meta.json)."""
    torch = _require_torch()

    driver = None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5, check=True).stdout.strip().splitlines()
        driver = out[0] if out else None
    except Exception:
        pass
    return {
        "torch": torch.__version__,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "cuda_available": torch.cuda.is_available(),
        "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        "driver_version": driver,
        "seed": SEED,
        "python": platform.python_version(),
    }


def run_experiment(n_runs, stress=False):
    torch = _require_torch()
    import torch.nn.functional as F
    import torchvision

    if not torch.cuda.is_available():
        raise SystemExit("[ERROR] --workload gpu requested but CUDA is not available")

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    batch = STRESS_BATCH if stress else BATCH
    model = torchvision.models.resnet18(num_classes=NUM_CLASSES).cuda().train()
    opt = torch.optim.SGD(model.parameters(), lr=1e-3, momentum=0.9)
    x = torch.randn(batch, 3, 224, 224, device="cuda")
    y = torch.randint(0, NUM_CLASSES, (batch,), device="cuda")

    def step():
        opt.zero_grad(set_to_none=True)
        F.cross_entropy(model(x), y).backward()
        opt.step()
        torch.cuda.synchronize()   # include GPU time in the measurement

    for _ in range(WARMUP_RUNS):
        step()

    times = []
    for _ in range(n_runs):
        start = time.perf_counter()
        step()
        times.append(time.perf_counter() - start)
    return np.array(times)
