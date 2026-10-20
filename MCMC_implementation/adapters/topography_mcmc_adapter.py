"""
Python adapter/wrapper around Niya's unchanged MCMC implementation.

Design rules (see docs/specification.md):
- Do not rewrite Niya's internal iteration loop into step().
- Drive the existing chain_crf.run(n_iter) interface in finite batches.
- Preserve bed + RNG state between batches so run(K) chunks can match a
  continuous run when proposal counts are aligned.
- MVP PT will swap temperatures via get/set_temperature; full bed
  export/import is optional.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

import numpy as np

# Prefer the project-local scientific package copy.
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from gstatsMCMC import MCMC, Topography  # noqa: E402

from .spectral_rng_overlay import install_spectral_rng_overlay  # noqa: E402

# Keep Niya's MCMC.py unchanged; overlay only redirects spectral noise to RF.rng.
install_spectral_rng_overlay(MCMC)


class TopographyMCMCAdapter:
    """Wrap a configured `chain_crf` + `RandField` without modifying Niya's loop."""

    def __init__(self) -> None:
        self.chain: Optional[MCMC.chain_crf] = None
        self.rf: Optional[MCMC.RandField] = None
        self._rng: Optional[np.random.Generator] = None
        self._temperature: float = 1.0
        self._energy: Optional[float] = None
        self._energy_mc: Optional[float] = None
        self._energy_data: Optional[float] = None
        self._current_bed: Optional[np.ndarray] = None
        self._proposals_completed: int = 0
        self._batches_completed: int = 0
        self._last_result: Optional[dict[str, Any]] = None
        self._initialized: bool = False

    def initialize(
        self,
        chain: MCMC.chain_crf,
        rf: MCMC.RandField,
        *,
        rng_seed: int | np.random.Generator = 0,
        temperature: float = 1.0,
    ) -> None:
        """Attach an already-configured scientific chain and random-field object."""
        if not isinstance(chain, MCMC.chain_crf):
            raise TypeError("chain must be an MCMC.chain_crf instance")
        if not isinstance(rf, MCMC.RandField):
            raise TypeError("rf must be an MCMC.RandField instance")

        self.chain = chain
        self.rf = rf
        self._rng = (
            rng_seed
            if isinstance(rng_seed, np.random.Generator)
            else np.random.default_rng(rng_seed)
        )
        self._temperature = float(temperature)
        self._current_bed = np.array(chain.initial_bed, copy=True)
        self._energy = None
        self._energy_mc = None
        self._energy_data = None
        self._proposals_completed = 0
        self._batches_completed = 0
        self._last_result = None
        self._initialized = True

    def run_batch(self, n_iterations: int) -> dict[str, Any]:
        """
        Run a finite batch through the existing scientific `run(n_iter)` API.

        Important Niya behavior:
        - `run(n)` records the starting bed at index 0 and performs (n - 1) proposals.
        - Each call starts from `chain.initial_bed`.
        - Passing an int seed restarts the chain RNG; we pass a live Generator instead.
        - `RandField` keeps its own RNG on the shared `rf` object across batches.
        """
        self._require_initialized()
        if n_iterations < 2:
            raise ValueError(
                "n_iterations must be >= 2 because Niya's run(n) only proposes "
                "on iterations 1..n-1 (index 0 is the starting state)."
            )

        assert self.chain is not None and self.rf is not None and self._rng is not None

        # Resume from the bed left by the previous batch.
        self.chain.initial_bed = np.array(self._current_bed, copy=True)

        result = self.chain.run(
            n_iterations,
            self.rf,
            rng_seed=self._rng,
            only_save_last_bed=True,
            info_per_iter=max(n_iterations, 1),
            plot=False,
            progress_bar=False,
        )
        bed_c, loss_mc, loss_data, loss, steps, resampled_times, blocks = result

        proposals = n_iterations - 1
        self._current_bed = np.array(bed_c, copy=True)
        self.chain.initial_bed = np.array(bed_c, copy=True)
        # Recompute energy from the final bed. Niya's run() updates mass-conservation
        # residuals incrementally; batch boundaries recompute from scratch, so the
        # cached loss[-1] can drift slightly even when beds match bit-for-bit.
        self._refresh_energy_from_bed()
        self._proposals_completed += proposals
        self._batches_completed += 1

        self._last_result = {
            "bed": self._current_bed,
            "loss": np.asarray(loss),
            "loss_mc": np.asarray(loss_mc),
            "loss_data": np.asarray(loss_data),
            "steps": np.asarray(steps),
            "blocks": np.asarray(blocks),
            "resampled_times": np.asarray(resampled_times),
            "proposals_this_batch": proposals,
            "proposals_completed": self._proposals_completed,
            "temperature": self._temperature,
            "energy": self._energy,
        }
        return self._last_result

    def get_energy(self) -> float:
        self._require_initialized()
        if self._energy is None:
            raise RuntimeError("No energy yet; call run_batch() first")
        return float(self._energy)

    def get_temperature(self) -> float:
        return float(self._temperature)

    def set_temperature(self, temperature: float) -> None:
        """
        Assign this replica's temperature.

        NOTE: Niya's current accept/reject rule does not yet consume temperature.
        Documented investigation task: inject T into local acceptance with a
        minimal wrapper/extension only if required. See
        docs/pt_temperature_energy_investigation.md.
        """
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        self._temperature = float(temperature)

    def get_metadata(self) -> dict[str, Any]:
        self._require_initialized()
        bed = self._current_bed
        return {
            "model_id": "chain_crf",
            "temperature": self._temperature,
            "energy": self._energy,
            "energy_mc": self._energy_mc,
            "energy_data": self._energy_data,
            "proposals_completed": self._proposals_completed,
            "batches_completed": self._batches_completed,
            "bed_shape": None if bed is None else tuple(bed.shape),
            "bed_dtype": None if bed is None else str(bed.dtype),
        }

    def checkpoint(self) -> dict[str, Any]:
        """Capture bed + RNG state needed to resume after a pause/exchange."""
        self._require_initialized()
        assert self.rf is not None and self._rng is not None
        return {
            "current_bed": np.array(self._current_bed, copy=True),
            "temperature": self._temperature,
            "energy": self._energy,
            "energy_mc": self._energy_mc,
            "energy_data": self._energy_data,
            "proposals_completed": self._proposals_completed,
            "batches_completed": self._batches_completed,
            "chain_rng_state": deepcopy(self._rng.bit_generator.state),
            "rf_rng_state": deepcopy(self.rf.rng.bit_generator.state),
        }

    def restore_checkpoint(self, ckpt: dict[str, Any]) -> None:
        self._require_initialized()
        assert self.chain is not None and self.rf is not None and self._rng is not None

        self._current_bed = np.array(ckpt["current_bed"], copy=True)
        self.chain.initial_bed = np.array(self._current_bed, copy=True)
        self._temperature = float(ckpt["temperature"])
        self._energy = ckpt.get("energy")
        self._energy_mc = ckpt.get("energy_mc")
        self._energy_data = ckpt.get("energy_data")
        self._proposals_completed = int(ckpt["proposals_completed"])
        self._batches_completed = int(ckpt["batches_completed"])
        self._rng.bit_generator.state = deepcopy(ckpt["chain_rng_state"])
        self.rf.rng.bit_generator.state = deepcopy(ckpt["rf_rng_state"])
        if self._current_bed is not None:
            self._refresh_energy_from_bed()

    # Optional physical state path (not required for MVP temperature-exchange PT)
    def export_state(self) -> bytes:
        self._require_initialized()
        assert self._current_bed is not None
        from io import BytesIO

        buf = BytesIO()
        np.savez_compressed(
            buf,
            bed=self._current_bed,
            temperature=np.array([self._temperature]),
            energy=np.array([np.nan if self._energy is None else self._energy]),
        )
        return buf.getvalue()

    def import_state(self, payload: bytes) -> None:
        self._require_initialized()
        assert self.chain is not None
        from io import BytesIO

        data = np.load(BytesIO(payload))
        bed = np.array(data["bed"], copy=True)
        self._current_bed = bed
        self.chain.initial_bed = np.array(bed, copy=True)
        self._temperature = float(data["temperature"][0])
        energy = float(data["energy"][0])
        self._energy = None if np.isnan(energy) else energy
        # Derived residuals/loss must be recomputed from the imported bed on the
        # next run_batch() call (Niya recomputes loss from initial_bed at start).

    def get_current_bed(self) -> np.ndarray:
        self._require_initialized()
        assert self._current_bed is not None
        return np.array(self._current_bed, copy=True)

    @staticmethod
    def proposals_in_run(n_iterations: int) -> int:
        """Niya's run(n) performs n-1 proposals."""
        return max(0, n_iterations - 1)

    @staticmethod
    def continuous_n_iter_for_batches(batch_n_iter: int, n_batches: int) -> int:
        """
        Choose continuous run(n) length so proposal count matches n_batches of
        run(batch_n_iter) under Niya's index-0-is-start convention.
        """
        return 1 + n_batches * TopographyMCMCAdapter.proposals_in_run(batch_n_iter)

    def _refresh_energy_from_bed(self) -> None:
        """Set energy fields from a full loss evaluation on `_current_bed`."""
        assert self.chain is not None and self._current_bed is not None
        bed = self._current_bed
        mc_res = Topography.get_mass_conservation_residual(
            bed,
            self.chain.surf,
            self.chain.velx,
            self.chain.vely,
            self.chain.dhdt,
            self.chain.smb,
            self.chain.resolution,
        )
        data_diff = bed - self.chain.cond_bed
        total, loss_mc, loss_data = self.chain.loss(mc_res, data_diff)
        self._energy = float(total)
        self._energy_mc = float(loss_mc)
        self._energy_data = float(loss_data)

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter is not initialized; call initialize() first")


def build_synthetic_crf_pair(
    *,
    rows: int = 24,
    cols: int = 24,
    resolution: float = 500.0,
    chain_seed: int = 0,
    rf_seed: int = 1,
):
    """
    Build a tiny configured (chain_crf, RandField) pair for local unit tests.

    This avoids depending on Stancomb-Wills CSV availability during adapter work.
    """
    x = np.arange(cols) * resolution
    y = np.arange(rows) * resolution
    xx, yy = np.meshgrid(x, y)

    # Gentle bowl + noise so mass-conservation residual is nonzero but stable.
    initial_bed = -200.0 - 0.001 * ((xx - xx.mean()) ** 2 + (yy - yy.mean()) ** 2)
    surf = initial_bed + 400.0
    velx = np.full_like(initial_bed, 20.0)
    vely = np.full_like(initial_bed, 5.0)
    dhdt = np.zeros_like(initial_bed)
    smb = np.full_like(initial_bed, 0.3)
    grounded = np.ones_like(initial_bed)
    cond_bed = initial_bed.copy()
    cond_bed[::4, ::4] = initial_bed[::4, ::4]
    data_mask = np.zeros_like(initial_bed)
    data_mask[::4, ::4] = 1

    chain = MCMC.chain_crf(
        xx,
        yy,
        initial_bed,
        surf,
        velx,
        vely,
        dhdt,
        smb,
        cond_bed,
        data_mask,
        grounded,
        resolution,
    )
    chain.set_update_region(True, grounded)
    chain.set_loss_type(map_func="sumsquare", sigma_mc=5.0, massConvInRegion=True)
    chain.set_update_type("CRF_weight")

    rf = MCMC.RandField(
        range_min_x=2_000,
        range_max_x=6_000,
        range_min_y=2_000,
        range_max_y=6_000,
        scale_min=5.0,
        scale_max=15.0,
        nugget_max=0.0,
        model_name="Gaussian",
        isotropic=True,
        rng_seed=rf_seed,
    )
    rf.set_block_sizes(3, 7, 3, 7, 5)
    rf.set_weight_param(
        logis_func_L=1.0,
        logis_func_x0=0.5,
        logis_func_k=1.0,
        logis_func_offset=0.0,
        max_dist=2_000.0,
        resolution=resolution,
    )
    rf.set_generation_method(spectral=True)
    chain.set_crf_data_weight(rf)

    # Keep chain_seed available to the caller for the adapter RNG.
    _ = chain_seed
    return chain, rf
