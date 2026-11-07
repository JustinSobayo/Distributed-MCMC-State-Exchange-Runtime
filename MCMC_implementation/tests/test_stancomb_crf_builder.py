"""Stancomb T3 builder smoke tests (skipped if CSV/bed missing)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.stancomb_crf import DEFAULT_DATA_DIR, build_stancomb_crf_pair  # noqa: E402
from benchmarks.single_chain_baseline import _validated_config  # noqa: E402


_CSV = DEFAULT_DATA_DIR / "StancombWillsDataGridded.csv"
_BED = DEFAULT_DATA_DIR / "sgs_bed.txt"
_HAS_DATA = _CSV.is_file() and _BED.is_file()


class StancombConfigTests(unittest.TestCase):
    def test_stancomb_yaml_settings_validate(self):
        resolved = _validated_config({
            "experiment": {"name": "stancomb_test", "seed": 1},
            "science": {"problem": "stancomb", "sigma_mc": 3.0},
            "sampling": {"num_batches": 1, "batch_n_iterations": 2},
            "runtime": {"output_dir": "results/tmp_stancomb"},
        })
        self.assertEqual(resolved["science"]["problem"], "stancomb")
        self.assertEqual(resolved["science"]["sigma_mc"], 3.0)


@unittest.skipUnless(_HAS_DATA, "Stancomb CSV/sgs_bed not present")
class StancombBuilderTests(unittest.TestCase):
    def test_build_returns_configured_pair(self):
        chain, rf = build_stancomb_crf_pair(chain_seed=0, rf_seed=1)
        self.assertEqual(chain.initial_bed.shape, chain.xx.shape)
        self.assertTrue(hasattr(rf, "pairs"))
        self.assertGreater(len(rf.pairs), 0)


if __name__ == "__main__":
    unittest.main()
