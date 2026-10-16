import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from gpu_sampler import parse_smi_output, summarize  # noqa: E402

SAMPLE = "0, 87, 10240, 245.31, 71, 1410\n1, 3, 512, [N/A], 40, 210\n"


def test_parse_two_gpus_and_na():
    rows = parse_smi_output(SAMPLE, ts=1.0)
    assert len(rows) == 2
    assert rows[0]["util_pct"] == 87.0 and rows[0]["sm_mhz"] == 1410.0
    assert rows[1]["power_w"] is None


def test_parse_skips_malformed_lines():
    assert parse_smi_output("garbage\n\n1,2,3", ts=1.0) == []


def test_summarize_ignores_none():
    s = summarize([{"util_pct": 50.0, "power_w": None}, {"util_pct": 70.0, "power_w": None}])
    assert s["util_pct_mean"] == 60.0 and s["util_pct_max"] == 70.0
    assert "power_w_mean" not in s and s["n_samples"] == 2
