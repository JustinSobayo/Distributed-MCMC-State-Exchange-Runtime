"""Stancomb enablement for the two-replica PT stack."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from adapters.stancomb_crf import DEFAULT_DATA_DIR  # noqa: E402
from workers.problem_factory import (  # noqa: E402
    build_replica_chain,
    science_fingerprint,
    science_metadata,
)
from workers.pt_coordinator import PTCoordinator, load_pt_config, validate_pt_config  # noqa: E402
from workers.replica_worker import ReplicaWorkerConfig, build_worker  # noqa: E402

_CSV = DEFAULT_DATA_DIR / "StancombWillsDataGridded.csv"
_BED = DEFAULT_DATA_DIR / "sgs_bed.txt"
_HAS_DATA = _CSV.is_file() and _BED.is_file()


class ValidateStancombPTConfigTests(unittest.TestCase):
    @unittest.skipUnless(_HAS_DATA, "Stancomb CSV/sgs_bed not present")
    def test_accepts_stancomb_dual_cold_and_pt_yamls(self):
        cold, _ = load_pt_config(_ROOT / "configs" / "two_replica_stancomb_baseline_cold.yaml")
        pt, _ = load_pt_config(_ROOT / "configs" / "two_replica_stancomb_pt.yaml")
        self.assertEqual(cold["science"]["problem"], "stancomb")
        self.assertFalse(cold["exchange"]["enabled"])
        self.assertEqual(cold["sampling"]["temperatures"], [1.0, 1.0])
        self.assertEqual(pt["science"]["problem"], "stancomb")
        self.assertTrue(pt["exchange"]["enabled"])
        self.assertEqual(pt["sampling"]["temperatures"], [1.0, 1.01])
        self.assertEqual(cold["sampling"]["batch_n_iterations"], pt["sampling"]["batch_n_iterations"])
        self.assertEqual(cold["sampling"]["rounds"], pt["sampling"]["rounds"])
        self.assertEqual(cold["sampling"]["rounds"], 600)

    def test_rejects_missing_stancomb_data_dir(self):
        with self.assertRaises(ValueError):
            validate_pt_config(
                {
                    "science": {
                        "problem": "stancomb",
                        "data_dir": str(_REPO / "does_not_exist_data"),
                        "sigma_mc": 3.0,
                    },
                    "exchange": {"enabled": False},
                    "sampling": {"temperatures": [1.0, 1.0], "rounds": 1, "batch_n_iterations": 3},
                }
            )

    def test_rejects_non_positive_sigma_mc(self):
        with self.assertRaises(ValueError):
            validate_pt_config(
                {
                    "science": {"problem": "stancomb", "sigma_mc": 0.0},
                    "exchange": {"enabled": False},
                    "sampling": {"temperatures": [1.0, 1.0]},
                }
            )

    def test_synthetic_still_valid(self):
        cfg = validate_pt_config({"science": {"problem": "synthetic"}, "exchange": {"enabled": True}})
        self.assertEqual(cfg["science"]["problem"], "synthetic")


class ProblemFactoryTests(unittest.TestCase):
    def test_synthetic_factory_shape(self):
        chain, _rf = build_replica_chain("synthetic", rf_seed=1, rows=24, cols=24)
        self.assertEqual(tuple(chain.initial_bed.shape), (24, 24))
        meta = science_metadata("synthetic", chain, data_dir=None, sigma_mc=3.0)
        self.assertEqual(meta["problem"], "synthetic")
        self.assertIsNone(meta["data_dir"])
        self.assertIsNone(meta["sigma_mc"])

    @unittest.skipUnless(_HAS_DATA, "Stancomb CSV/sgs_bed not present")
    def test_stancomb_factory_shape(self):
        chain, _rf = build_replica_chain(
            "stancomb", rf_seed=1, data_dir=DEFAULT_DATA_DIR, sigma_mc=3.0
        )
        self.assertEqual(tuple(chain.initial_bed.shape), (500, 500))
        meta = science_metadata(
            "stancomb", chain, data_dir=DEFAULT_DATA_DIR, sigma_mc=3.0
        )
        self.assertEqual(meta["bed_shape"], [500, 500])
        self.assertEqual(meta["sigma_mc"], 3.0)


class CoordinatorFingerprintTests(unittest.TestCase):
    def _coord(self, problem: str = "stancomb") -> PTCoordinator:
        if problem == "stancomb":
            cfg = validate_pt_config(
                {
                    "science": {
                        "problem": "stancomb",
                        "data_dir": str(DEFAULT_DATA_DIR),
                        "sigma_mc": 3.0,
                    },
                    "exchange": {"enabled": False},
                    "sampling": {"temperatures": [1.0, 1.0], "rounds": 1, "batch_n_iterations": 3},
                    "logging": {"terminal": False},
                }
            )
        else:
            cfg = validate_pt_config(
                {
                    "science": {"problem": "synthetic"},
                    "exchange": {"enabled": True},
                    "logging": {"terminal": False},
                }
            )
        return PTCoordinator(cfg)

    def test_mismatch_problems_halt(self):
        coord = self._coord("synthetic")
        reader = MagicMock()
        writer = MagicMock()
        from workers.pt_coordinator import WorkerConn

        coord.workers[0] = WorkerConn(
            0, reader, writer, 1.0,
            {"problem": "synthetic", "bed_shape": [24, 24], "data_dir": None, "sigma_mc": None},
        )
        coord.workers[1] = WorkerConn(
            1, reader, writer, 1.0,
            {"problem": "stancomb", "bed_shape": [500, 500], "data_dir": "/x", "sigma_mc": 3.0},
        )
        with self.assertRaises(RuntimeError):
            coord._assert_matching_science()

    def test_matching_synthetic_ok(self):
        coord = self._coord("synthetic")
        from workers.pt_coordinator import WorkerConn

        meta = {"problem": "synthetic", "bed_shape": [24, 24], "data_dir": None, "sigma_mc": None}
        coord.workers[0] = WorkerConn(0, MagicMock(), MagicMock(), 1.0, meta)
        coord.workers[1] = WorkerConn(1, MagicMock(), MagicMock(), 2.0, dict(meta))
        out = coord._assert_matching_science()
        self.assertEqual(science_fingerprint(out), science_fingerprint(meta))


@unittest.skipUnless(_HAS_DATA, "Stancomb CSV/sgs_bed not present")
class StancombWorkerBuildTests(unittest.TestCase):
    def test_worker_register_includes_science(self):
        worker = build_worker(
            ReplicaWorkerConfig(
                replica_id=0,
                temperature=1.0,
                coordinator_host="127.0.0.1",
                coordinator_port=9,
                problem="stancomb",
                data_dir=str(DEFAULT_DATA_DIR),
                sigma_mc=3.0,
            )
        )
        register = worker.register_message()
        self.assertEqual(register["problem"], "stancomb")
        self.assertEqual(register["bed_shape"], [500, 500])
        self.assertEqual(register["sigma_mc"], 3.0)
        self.assertIn("data_dir", register)


if __name__ == "__main__":
    unittest.main()
