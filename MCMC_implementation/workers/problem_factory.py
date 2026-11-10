"""Select synthetic vs Stancomb chain builders for replica workers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.stancomb_crf import build_stancomb_crf_pair, resolve_data_dir
from adapters.topography_mcmc_adapter import build_synthetic_crf_pair


def build_replica_chain(
    problem: str,
    *,
    rf_seed: int,
    chain_seed: int = 0,
    data_dir: str | Path | None = None,
    sigma_mc: float = 3.0,
    rows: int = 24,
    cols: int = 24,
    resolution: float = 500.0,
):
    """Return ``(chain_crf, RandField)`` for the configured scientific problem."""
    if problem == "synthetic":
        return build_synthetic_crf_pair(
            rows=rows,
            cols=cols,
            resolution=resolution,
            chain_seed=chain_seed,
            rf_seed=rf_seed,
        )
    if problem == "stancomb":
        return build_stancomb_crf_pair(
            data_dir=data_dir,
            sigma_mc=sigma_mc,
            chain_seed=chain_seed,
            rf_seed=rf_seed,
        )
    raise ValueError(f"unsupported science.problem: {problem!r}")


def science_metadata(
    problem: str,
    chain,
    *,
    data_dir: str | Path | None,
    sigma_mc: float,
) -> dict[str, Any]:
    """Fields included in REGISTER so the coordinator can fingerprint workers."""
    bed = getattr(chain, "initial_bed", None)
    if bed is None:
        raise ValueError("chain has no initial_bed for science fingerprint")
    resolved_dir = None
    sigma = None
    if problem == "stancomb":
        resolved_dir = str(resolve_data_dir(data_dir))
        sigma = float(sigma_mc)
    return {
        "problem": problem,
        "bed_shape": [int(bed.shape[0]), int(bed.shape[1])],
        "data_dir": resolved_dir,
        "sigma_mc": sigma,
    }


def science_fingerprint(meta: dict[str, Any]) -> tuple[Any, ...]:
    """Comparable key for REGISTER science metadata."""
    shape = meta.get("bed_shape")
    if isinstance(shape, (list, tuple)):
        shape_key = tuple(int(x) for x in shape)
    else:
        shape_key = None
    return (
        meta.get("problem"),
        shape_key,
        meta.get("data_dir"),
        meta.get("sigma_mc"),
    )
