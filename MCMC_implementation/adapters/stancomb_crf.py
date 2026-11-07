"""Build a Bakari T3-style Stancomb-Wills (chain_crf, RandField) pair.

Mirrors ``notebooks/T3_LargeScaleChain.ipynb`` construction only — no ``run()``.
Variogram parameters are the fixed T3 values (cell that sets ``V1_p = [...]``)
so baselines stay reproducible without re-fitting skg every launch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from gstatsMCMC import MCMC  # noqa: E402

# Frozen from T3_LargeScaleChain.ipynb (Matern fit used for RF smoothness / max_dist).
T3_VARIOGRAM_PARAMS = (135866.77378305534, 2.2455698864420484, 3.038653872208876, 0.0)
DEFAULT_DATA_DIR = _PKG_ROOT / "data"


def _resolve_data_dir(data_dir: str | Path | None) -> Path:
    if data_dir is None:
        return DEFAULT_DATA_DIR
    path = Path(data_dir)
    if not path.is_absolute():
        # Allow repo-relative paths from the YAML / CLI cwd.
        repo_root = _PKG_ROOT.parent
        candidate = (repo_root / path).resolve()
        if candidate.is_dir():
            return candidate
        candidate = (_PKG_ROOT / path).resolve()
        if candidate.is_dir():
            return candidate
    return path.resolve()


def load_stancomb_maps(data_dir: str | Path | None = None) -> dict[str, Any]:
    """Load CSV + SGS init bed the same way T3 does before ``chain_crf``."""
    root = _resolve_data_dir(data_dir)
    csv_path = root / "StancombWillsDataGridded.csv"
    bed_path = root / "sgs_bed.txt"
    if not csv_path.is_file():
        raise FileNotFoundError(f"missing Stancomb CSV: {csv_path}")
    if not bed_path.is_file():
        raise FileNotFoundError(f"missing SGS init bed: {bed_path}")

    df = pd.read_csv(csv_path)
    x_uniq = np.unique(df.x)
    y_uniq = np.unique(df.y)
    resolution = 500.0
    xx, yy = np.meshgrid(x_uniq, y_uniq)

    dhdt = df["dhdt"].values.reshape(xx.shape)
    smb = df["smb"].values.reshape(xx.shape)
    velx = df["velx"].values.reshape(xx.shape)
    vely = df["vely"].values.reshape(xx.shape)
    bedmap_mask = df["bedmap_mask"].values.reshape(xx.shape)
    bedmachine_thickness = df["bedmachine_thickness"].values.reshape(xx.shape)
    bedmap_surf = df["bedmap_surf"].values.reshape(xx.shape)
    highvel_mask = df["highvel_mask"].values.reshape(xx.shape)
    bedmap_bed = df["bedmap_bed"].values.reshape(xx.shape)
    bedmachine_bed = bedmap_surf - bedmachine_thickness

    cond_bed = np.where(bedmap_mask == 1, df["bed"].values.reshape(xx.shape), bedmap_bed)
    data_mask = ~np.isnan(cond_bed)
    grounded_ice_mask = bedmap_mask == 1

    sgs_bed = np.loadtxt(bed_path)
    if sgs_bed.shape != xx.shape:
        raise ValueError(f"sgs_bed shape {sgs_bed.shape} != grid {xx.shape}")
    thickness = bedmap_surf - sgs_bed
    sgs_bed = np.where((thickness <= 0) & (bedmap_mask == 1), bedmap_surf - 1, sgs_bed)

    return {
        "data_dir": root,
        "xx": xx,
        "yy": yy,
        "resolution": resolution,
        "sgs_bed": sgs_bed,
        "bedmap_surf": bedmap_surf,
        "velx": velx,
        "vely": vely,
        "dhdt": dhdt,
        "smb": smb,
        "cond_bed": cond_bed,
        "data_mask": data_mask,
        "grounded_ice_mask": grounded_ice_mask,
        "highvel_mask": highvel_mask,
        "bedmap_mask": bedmap_mask,
        "bedmachine_bed": bedmachine_bed,
    }


def build_stancomb_crf_pair(
    *,
    data_dir: str | Path | None = None,
    sigma_mc: float = 3.0,
    chain_seed: int = 0,
    rf_seed: int = 1,
    variogram_params: tuple[float, float, float, float] = T3_VARIOGRAM_PARAMS,
):
    """Return a configured ``(chain_crf, RandField)`` matching Bakari T3 setup.

    ``chain_seed`` is accepted for API symmetry with the synthetic builder; the
    adapter owns the live chain RNG after ``initialize``.
    """
    maps = load_stancomb_maps(data_dir)
    resolution = float(maps["resolution"])
    range_, _sill, smoothness, _nugget = (float(x) for x in variogram_params)

    chain = MCMC.chain_crf(
        maps["xx"],
        maps["yy"],
        maps["sgs_bed"],
        maps["bedmap_surf"],
        maps["velx"],
        maps["vely"],
        maps["dhdt"],
        maps["smb"],
        maps["cond_bed"],
        maps["data_mask"],
        maps["grounded_ice_mask"],
        resolution,
    )
    chain.set_update_region(True, maps["highvel_mask"])
    chain.set_loss_type(map_func="sumsquare", sigma_mc=float(sigma_mc), massConvInRegion=True)

    rf = MCMC.RandField(
        range_min_x=10e3,
        range_max_x=50e3,
        range_min_y=10e3,
        range_max_y=50e3,
        scale_min=1.0,
        scale_max=1500.0,
        nugget_max=0.0,
        model_name="Matern",
        isotropic=True,
        smoothness=smoothness,
        rng_seed=rf_seed,
    )
    rf.set_block_sizes(50, 80, 50, 80)
    rf.set_weight_param(
        logis_func_L=2.0,
        logis_func_x0=0.0,
        logis_func_k=6.0,
        logis_func_offset=1.0,
        max_dist=range_,
        resolution=resolution,
    )
    rf.set_generation_method(spectral=True)
    # Prefer computed CRF weights (T3 cell with set_crf_data_weight); data_weight.txt
    # is not shipped in this repo.
    chain.set_crf_data_weight(rf)
    chain.set_update_type("CRF_weight")

    _ = chain_seed
    return chain, rf
