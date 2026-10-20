"""
Runtime overlay for checkpoint-safe spectral proposals.

Niya's `spectral_synthesis_field` (source of truth) draws FFT/nugget noise via
global `np.random.normal`. That stream is not part of `RandField.rng`, so
batch/checkpoint resume cannot restore it.

This module does **not** edit her science code. It wraps her function and, only
for the duration of each call, routes `np.random.normal` through `RF.rng` so the
adapter can checkpoint one Generator.

Not safe if two replicas share one process and call this concurrently.
"""

from __future__ import annotations

import numpy as np

_PATCHED = False
_ORIGINAL = None


def install_spectral_rng_overlay(mcmc_module) -> None:
    """Replace `mcmc_module.spectral_synthesis_field` with a resumable wrapper."""
    global _PATCHED, _ORIGINAL
    if _PATCHED:
        return

    _ORIGINAL = mcmc_module.spectral_synthesis_field
    original_normal = np.random.normal

    def spectral_synthesis_field(RF, shape, res=1.0):
        rng = RF.rng

        def normal_via_rf_rng(*args, **kwargs):
            loc = kwargs["loc"] if "loc" in kwargs else (args[0] if len(args) > 0 else 0.0)
            scale = kwargs["scale"] if "scale" in kwargs else (args[1] if len(args) > 1 else 1.0)
            size = kwargs["size"] if "size" in kwargs else (args[2] if len(args) > 2 else None)
            return rng.normal(loc=loc, scale=scale, size=size)

        np.random.normal = normal_via_rf_rng  # type: ignore[assignment]
        try:
            return _ORIGINAL(RF, shape, res=res)
        finally:
            np.random.normal = original_normal  # type: ignore[assignment]

    mcmc_module.spectral_synthesis_field = spectral_synthesis_field
    _PATCHED = True
