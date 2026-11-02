"""Validate the prepared Stancomb-Wills CSV and export a lossless NetCDF grid."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BACKEND.parent / "MCMC_implementation/data/StancombWillsDataGridded.csv"
REQUIRED = {"x", "y", "surf", "bed", "velx", "vely", "smb", "dhdt",
            "highvel_mask", "bedmap_mask", "bedmap_surf", "bedmachine_source",
            "bedmachine_thickness", "bedmap_bed"}
HEIGHTS = {"surf", "bed", "bedmap_surf", "bedmachine_thickness", "bedmap_bed", "bedmachine_bed"}


def build_grid(source: Path, bbox=None):
    """Use actual coordinate pairs, never the CSV row order, to construct (y,x)."""
    source = Path(source)
    frame = pd.read_csv(source)
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Input CSV is empty")
    for name in frame.columns:
        if name == "highvel_mask":
            mapped = frame[name].astype(str).str.lower().map({"true": 1, "false": 0, "1": 1, "0": 0})
            if mapped.isna().any():
                raise ValueError("highvel_mask must contain true/false or 0/1")
            frame[name] = mapped
        else:
            frame[name] = pd.to_numeric(frame[name], errors="raise")
        if np.isinf(frame[name].to_numpy(dtype=float)).any():
            raise ValueError(f"Infinite values in {name}")
    if frame[["x", "y"]].isna().any().any():
        raise ValueError("Coordinates cannot be missing")
    if frame.duplicated(["x", "y"]).any():
        raise ValueError("Duplicate coordinate pairs")
    if bbox is not None:
        west, south, east, north = bbox
        if not np.isfinite(bbox).all() or west >= east or south >= north:
            raise ValueError("bbox must be finite xmin ymin xmax ymax with increasing bounds")
        frame = frame.loc[frame.x.between(west, east) & frame.y.between(south, north)].copy()
    if frame.empty:
        raise ValueError("Crop contains no cells")
    x, y = np.sort(frame.x.unique()), np.sort(frame.y.unique())
    for name, coords in [("x", x), ("y", y)]:
        if len(coords) < 2 or not np.allclose(np.diff(coords), 500, rtol=0, atol=1e-6):
            raise ValueError(f"{name} must have at least two cells and regular 500 m spacing")
    if len(frame) != len(x) * len(y):
        raise ValueError("Grid has missing coordinate pairs")
    ordered = frame.set_index(["y", "x"]).reindex(pd.MultiIndex.from_product([y, x], names=["y", "x"]))
    ds = xr.Dataset(coords={"x": x, "y": y})
    for name in ordered.columns:
        values = ordered[name].to_numpy(dtype=float).reshape(len(y), len(x))
        ds[name] = (("y", "x"), values)
        ds[name].attrs["source_column"] = name
        if name in HEIGHTS:
            ds[name].attrs["units"] = "m"
        if name == "highvel_mask":
            ds[name].attrs.update(flag_values=np.array([0, 1], dtype="int32"), flag_meanings="false true")
    for name in ("x", "y"):
        ds[name].attrs.update(units="m", long_name=f"Source grid {name} coordinate")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    ds.attrs.update(title="Stancomb-Wills prepared repository grid", source_file=source.name,
                    source_sha256=sha, created_utc=datetime.now(timezone.utc).isoformat(),
                    coordinate_reference_status="Unconfirmed; original x/y retained; no reprojection performed",
                    vertical_reference_status="Unconfirmed; source elevations retained without correction",
                    processing="Coordinate validation and ordering only; no interpolation, filling, or scientific corrections",
                    grid_spacing_m=500)
    report = {"source_file": str(source.resolve()), "source_sha256": sha,
              "shape_y_x": [len(y), len(x)], "cells": len(frame), "spacing_m": 500,
              "cell_center_bounds": [float(x[0]), float(y[0]), float(x[-1]), float(y[-1])],
              "missing_by_variable": {n: int(ds[n].isnull().sum()) for n in ds.data_vars},
              "warnings": [ds.attrs["coordinate_reference_status"], ds.attrs["vertical_reference_status"],
                           "Velocity, smb, dhdt units and mask class meanings require source confirmation."]}
    return ds, report


def export_grid(source=DEFAULT_INPUT, output=None, bbox=None):
    """Export, reopen, and compare every value including missing cells."""
    output = Path(output or BACKEND / "generated/stancomb_wills.nc")
    if output.suffix.lower() != ".nc":
        raise ValueError("Output must have .nc extension")
    if output.resolve() == Path(source).resolve():
        raise ValueError("Output cannot replace input")
    ds, report = build_grid(Path(source), bbox)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".nc.tmp")
    try:
        ds.to_netcdf(temporary, engine="scipy", format="NETCDF3_64BIT")
        with xr.open_dataset(temporary, engine="scipy") as restored:
            xr.testing.assert_equal(ds, restored.load())
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    report["roundtrip_verified"] = True
    report_path = output.with_suffix(".validation.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output, report_path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=BACKEND / "generated/stancomb_wills.nc")
    parser.add_argument("--bbox", type=float, nargs=4, metavar=("XMIN", "YMIN", "XMAX", "YMAX"))
    args = parser.parse_args()
    try:
        output, report_path, report = export_grid(args.input, args.output, args.bbox)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(f"Verified {report['cells']} cells; shape (y,x)={report['shape_y_x']}")
    print(f"NetCDF: {output}\nReport: {report_path}")
    for warning in report["warnings"]:
        print(f"NOTE: {warning}")


if __name__ == "__main__":
    main()
