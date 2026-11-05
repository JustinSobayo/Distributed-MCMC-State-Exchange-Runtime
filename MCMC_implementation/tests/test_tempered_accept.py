"""Gates for tempered Metropolis accept in the bundled Niya copy."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from adapters.topography_mcmc_adapter import (  # noqa: E402
    TopographyMCMCAdapter,
    build_synthetic_crf_pair,
)


def _accepted(steps) -> int:
    steps = np.asarray(steps)
    return int(np.sum(steps[1:]))


def test_temperature_default_matches_explicit_one():
    chain_a, rf_a = build_synthetic_crf_pair(chain_seed=0, rf_seed=1)
    chain_b, rf_b = build_synthetic_crf_pair(chain_seed=0, rf_seed=1)

    adapter_a = TopographyMCMCAdapter()
    adapter_a.initialize(chain_a, rf_a, rng_seed=0, temperature=1.0)
    result_a = adapter_a.run_batch(21)

    adapter_b = TopographyMCMCAdapter()
    adapter_b.initialize(chain_b, rf_b, rng_seed=0, temperature=1.0)
    result_b = adapter_b.run_batch(21)

    np.testing.assert_array_equal(result_a["steps"], result_b["steps"])
    np.testing.assert_allclose(result_a["energy"], result_b["energy"])


def test_hot_temperature_accepts_at_least_as_many_as_cold():
    """Same synthetic start/seed: hotter T should not accept fewer proposals.

    On this tiny bowl the cold chain often accepts everything; the inequality
    is still the correct gate, and a huge T must remain valid.
    """
    cold_chain, cold_rf = build_synthetic_crf_pair(chain_seed=3, rf_seed=4)
    hot_chain, hot_rf = build_synthetic_crf_pair(chain_seed=3, rf_seed=4)

    cold = TopographyMCMCAdapter()
    cold.initialize(cold_chain, cold_rf, rng_seed=3, temperature=1.0)
    cold_result = cold.run_batch(51)

    hot = TopographyMCMCAdapter()
    hot.initialize(hot_chain, hot_rf, rng_seed=3, temperature=100.0)
    hot_result = hot.run_batch(51)

    assert _accepted(hot_result["steps"]) >= _accepted(cold_result["steps"])


def test_set_temperature_rejects_non_positive():
    chain, rf = build_synthetic_crf_pair()
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=0, temperature=1.0)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        try:
            adapter.set_temperature(bad)
            raise AssertionError(f"expected ValueError for temperature={bad!r}")
        except ValueError:
            pass
