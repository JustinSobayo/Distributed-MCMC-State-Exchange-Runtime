"""Fast baseline contract and synthetic integration tests (also pytest compatible)."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.single_chain_baseline import (  # noqa: E402
    _validated_config, accumulate_batch, run_baseline, running_accept,
)


class MetricsTests(unittest.TestCase):
    def test_excludes_start_and_accumulates(self):
        a1, n1 = accumulate_batch([0, 1, 0, 1], 3)
        a2, n2 = accumulate_batch([0, 0, 1], 2)
        self.assertEqual((a1, n1), (2, 3))
        self.assertEqual(running_accept(a1 + a2, n1 + n2), 3 / 5)
        self.assertEqual(running_accept(0, 0), 0.0)

    def test_refuses_unexpected_cache(self):
        for steps in ([1, 1, 0], [0, 1], [0, 0.5, 1], [[0, 1, 0]]):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                accumulate_batch(steps, 2)

    def test_invalid_counts(self):
        with self.assertRaises(ValueError):
            running_accept(3, 2)

    def test_invalid_settings(self):
        settings = [
            {"sampling": {"temperature": 2}},
            {"sampling": {"temperature": True}},
            {"sampling": {"num_batches": 0}},
            {"sampling": {"batch_n_iterations": 1}},
            {"sampling": {"batch_n_iterations": 3.5}},
            {"sampling": {"budget_mode": "wall_clock"}},
            {"science": {"backend": "cuda"}},
            {"science": {"problem": "glacier"}},
            {"science": {"config": "unused.yaml"}},
            {"science": {"sigma_mc": 0}},
            {"logging": {"log_every_batches": 0}},
            {"experiment": {"seed": -1}},
            {"sampling": {"num_batch": 2}},
        ]
        for config in settings:
            with self.subTest(config=config), self.assertRaises(ValueError):
                _validated_config(config)


class BaselineSmokeTests(unittest.TestCase):
    def test_synthetic_cpu_outputs_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {
                "experiment": {"seed": 1234, "rf_seed": 1235},
                "sampling": {"num_batches": 2, "batch_n_iterations": 3},
                "logging": {"terminal": True},
            }
            path = root / "smoke.yaml"
            path.write_text(yaml.safe_dump(config))
            terminal = io.StringIO()
            with contextlib.redirect_stdout(terminal):
                summary = run_baseline(path, output_dir=root / "first")
                repeated = run_baseline(path, output_dir=root / "second")
            self.assertEqual(summary["attempted"], 4)
            self.assertEqual(summary["batches_completed"], 2)
            self.assertEqual(summary["budget_mode"], "proposals")
            self.assertEqual(summary["a_local"], summary["accepted"] / 4)
            self.assertGreater(summary["wall_s"], 0)
            self.assertEqual(summary["proposals_per_second"], 4 / summary["wall_s"])
            self.assertEqual(summary["accepted"], repeated["accepted"])
            self.assertEqual(summary["energy_final"], repeated["energy_final"])
            fingerprint = summary["fingerprint"]
            self.assertEqual(fingerprint["temperature"], 1.0)
            self.assertIs(fingerprint["exchange"], False)
            self.assertEqual(fingerprint["problem"], "synthetic")
            self.assertEqual(fingerprint["backend"], "cpu")
            self.assertEqual(fingerprint["bed_shape"], [24, 24])
            self.assertEqual(fingerprint["rng_seed"], 1234)
            self.assertEqual(fingerprint["rf_seed"], 1235)
            self.assertEqual(fingerprint["config_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(fingerprint["sources"])
            self.assertTrue(fingerprint["package_versions"])
            self.assertEqual(json.loads((root / "first/summary.json").read_text()), summary)
            self.assertEqual(json.loads((root / "first/fingerprint.json").read_text()), fingerprint)
            with (root / "first/batch_metrics.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([int(row["attempted"]) for row in rows], [2, 4])
            self.assertEqual(sum(int(row["accepted_delta"]) for row in rows), summary["accepted"])
            self.assertEqual(float(rows[-1]["energy"]), summary["energy_final"])
            self.assertEqual(float(rows[-1]["wall_s"]), summary["wall_s"])
            self.assertIn("batch=2/2  proposals=4", terminal.getvalue())
            self.assertIn("BASELINE DONE  proposals=4", terminal.getvalue())
            self.assertEqual(len(terminal.getvalue().splitlines()), 6)

    def test_terminal_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "quiet.yaml"
            path.write_text(yaml.safe_dump({
                "sampling": {"num_batches": 1, "batch_n_iterations": 2},
                "logging": {"terminal": False},
            }))
            terminal = io.StringIO()
            with contextlib.redirect_stdout(terminal):
                summary = run_baseline(path, output_dir=root / "output")
            self.assertEqual(terminal.getvalue(), "")
            self.assertEqual(summary["attempted"], 1)


if __name__ == "__main__":
    unittest.main()
