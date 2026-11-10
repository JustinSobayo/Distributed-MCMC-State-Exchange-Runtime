"""Tests for Stancomb single-chain baseline plotting."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.plot_single_chain_baseline import load_run, render_run  # noqa: E402


def _write_fixture(run_dir: Path, *, problem: str = "stancomb", temperature: float = 1.0) -> None:
    rows = [
        {
            "batch": 1,
            "accepted_delta": 1,
            "attempted_delta": 2,
            "accepted": 1,
            "attempted": 2,
            "a_local": 0.5,
            "energy": 100.0,
            "batch_wall_s": 0.1,
            "wall_s": 0.1,
            "proposals_per_second": 20.0,
        },
        {
            "batch": 2,
            "accepted_delta": 2,
            "attempted_delta": 2,
            "accepted": 3,
            "attempted": 4,
            "a_local": 0.75,
            "energy": 90.0,
            "batch_wall_s": 0.1,
            "wall_s": 0.2,
            "proposals_per_second": 20.0,
        },
    ]
    with (run_dir / "batch_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    fingerprint = {
        "problem": problem,
        "temperature": temperature,
        "bed_shape": [500, 500],
        "exchange": False,
    }
    (run_dir / "fingerprint.json").write_text(json.dumps(fingerprint) + "\n")
    summary = {
        "accepted": 3,
        "attempted": 4,
        "a_local": 0.75,
        "energy_final": 90.0,
        "wall_s": 0.2,
        "proposals_per_second": 20.0,
        "fingerprint_id": "fixture",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary) + "\n")


class PlotSingleChainBaselineTests(unittest.TestCase):
    def test_render_writes_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            out_dir = Path(tmp) / "figures"
            run_dir.mkdir()
            _write_fixture(run_dir)
            manifest = render_run(run_dir, out_dir, prefix="fixture")
            self.assertTrue(Path(manifest["figures"]["energy_png"]).is_file())
            self.assertTrue(Path(manifest["figures"]["accept_png"]).is_file())
            self.assertTrue(Path(manifest["figures"]["throughput_png"]).is_file())
            self.assertTrue(Path(manifest["manifest_path"]).is_file())
            self.assertEqual(manifest["problem"], "stancomb")

    def test_rejects_non_stancomb(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            _write_fixture(run_dir, problem="synthetic")
            with self.assertRaises(ValueError):
                load_run(run_dir)

    def test_rejects_bakari_figures_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MCMC_implementation").mkdir()
            run_dir = root / "run"
            run_dir.mkdir()
            _write_fixture(run_dir)
            with self.assertRaises(ValueError):
                render_run(run_dir, root / "MCMC_implementation" / "figures")


if __name__ == "__main__":
    unittest.main()
