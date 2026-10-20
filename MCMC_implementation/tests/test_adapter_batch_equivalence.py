"""
Batch-equivalence tests for the topography MCMC adapter.

Niya's chain_crf.run(n) records the starting state at index 0 and only
proposes on iterations 1..n-1. Therefore:

    continuous n_iter = 1 + n_batches * (batch_n_iter - 1)

must be used when comparing one continuous run to repeated run_batch calls.
"""

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


def _run_continuous(n_iter: int, chain_seed: int = 0, rf_seed: int = 1):
    chain, rf = build_synthetic_crf_pair(chain_seed=chain_seed, rf_seed=rf_seed)
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=chain_seed, temperature=1.0)
    result = adapter.run_batch(n_iter)
    return adapter, result


def _run_batched(batch_n_iter: int, n_batches: int, chain_seed: int = 0, rf_seed: int = 1):
    chain, rf = build_synthetic_crf_pair(chain_seed=chain_seed, rf_seed=rf_seed)
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=chain_seed, temperature=1.0)
    last = None
    for _ in range(n_batches):
        last = adapter.run_batch(batch_n_iter)
    return adapter, last


def test_proposal_count_helper():
    assert TopographyMCMCAdapter.proposals_in_run(10) == 9
    assert TopographyMCMCAdapter.continuous_n_iter_for_batches(10, 10) == 91


def test_batched_run_matches_continuous_final_bed():
    batch_n_iter = 6
    n_batches = 4
    continuous_n = TopographyMCMCAdapter.continuous_n_iter_for_batches(
        batch_n_iter, n_batches
    )

    cont_adapter, cont = _run_continuous(continuous_n)
    batch_adapter, batched = _run_batched(batch_n_iter, n_batches)

    assert cont_adapter._proposals_completed == batch_adapter._proposals_completed
    assert cont["proposals_completed"] == batched["proposals_completed"]

    np.testing.assert_allclose(
        cont_adapter.get_current_bed(),
        batch_adapter.get_current_bed(),
        rtol=0.0,
        atol=0.0,
    )
    assert cont_adapter.get_energy() == batch_adapter.get_energy()


def test_checkpoint_restore_preserves_continuation():
    chain, rf = build_synthetic_crf_pair(chain_seed=7, rf_seed=8)
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=7)

    adapter.run_batch(5)
    ckpt = adapter.checkpoint()
    bed_after_first = adapter.get_current_bed()
    energy_after_first = adapter.get_energy()

    # Continue without restore (reference path)
    chain_ref, rf_ref = build_synthetic_crf_pair(chain_seed=7, rf_seed=8)
    ref = TopographyMCMCAdapter()
    ref.initialize(chain_ref, rf_ref, rng_seed=7)
    ref.run_batch(5)
    ref.run_batch(5)
    ref_bed = ref.get_current_bed()
    ref_energy = ref.get_energy()

    # Restore and continue
    chain2, rf2 = build_synthetic_crf_pair(chain_seed=7, rf_seed=8)
    restored = TopographyMCMCAdapter()
    restored.initialize(chain2, rf2, rng_seed=7)
    restored.restore_checkpoint(ckpt)
    np.testing.assert_array_equal(restored.get_current_bed(), bed_after_first)
    assert restored.get_energy() == energy_after_first

    restored.run_batch(5)
    np.testing.assert_array_equal(restored.get_current_bed(), ref_bed)
    assert restored.get_energy() == ref_energy


def test_temperature_get_set():
    chain, rf = build_synthetic_crf_pair()
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=0, temperature=1.0)
    adapter.set_temperature(2.5)
    assert adapter.get_temperature() == 2.5
    meta = adapter.get_metadata()
    assert meta["temperature"] == 2.5
