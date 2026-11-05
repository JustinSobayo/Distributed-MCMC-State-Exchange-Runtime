"""Integration smoke for the two-replica Python PT launcher."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent


def test_two_replica_pt_launcher_smoke():
    with tempfile.TemporaryDirectory(prefix="pt_smoke_") as tmp:
        output_dir = Path(tmp) / "out"
        config = {
            "experiment": {
                "name": "pt_smoke",
                "seed": 7,
                "rng_seed": 7,
                "rf_seed": 8,
                "coordinator_seed": 9,
            },
            "science": {
                "problem": "synthetic",
                "backend": "cpu",
                "config": None,
                "rows": 24,
                "cols": 24,
                "resolution": 500.0,
            },
            "sampling": {
                "replicas": 2,
                "temperatures": [1.0, 2.0],
                "batch_n_iterations": 3,
                "rounds": 2,
                "warmup_rounds": 0,
            },
            "exchange": {"enabled": True, "pairing": "two_replica"},
            "logging": {"terminal": False, "log_every_rounds": 1},
            "runtime": {
                "coordinator_host": "127.0.0.1",
                "coordinator_port": 0,
                "round_timeout_seconds": 120,
                "output_dir": str(output_dir),
            },
        }
        config_path = Path(tmp) / "pt_smoke.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))

        proc = subprocess.run(
            [
                sys.executable,
                str(_ROOT / "scripts" / "run_two_replica_pt.py"),
                "--config",
                str(config_path),
            ],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"launcher failed ({proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

        summary = json.loads((output_dir / "summary.json").read_text())
        assert summary["rounds"] == 2
        assert summary["exchange_enabled"] is True
        assert summary["swap_attempts"] == 2
        assert 0 <= summary["swap_accepts"] <= 2
        rounds = json.loads((output_dir / "round_metrics.json").read_text())
        assert len(rounds) == 2
        assert all(len(row["E"]) == 2 for row in rounds)
        assert all(row["cold_worker"] in (0, 1) for row in rounds)


def test_validate_cold_baseline_allows_two_ones():
    sys.path.insert(0, str(_ROOT))
    from workers.pt_coordinator import validate_pt_config

    config = validate_pt_config(
        {
            "sampling": {"temperatures": [1.0, 1.0], "rounds": 1, "batch_n_iterations": 3},
            "exchange": {"enabled": False},
        }
    )
    assert config["exchange"]["enabled"] is False
    assert config["sampling"]["temperatures"] == [1.0, 1.0]
