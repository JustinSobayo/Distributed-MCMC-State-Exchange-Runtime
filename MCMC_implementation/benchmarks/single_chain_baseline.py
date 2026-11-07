"""Single-process, T=1 baseline using the existing batched MCMC adapter."""

from __future__ import annotations

import csv
from contextlib import redirect_stdout
import hashlib
import importlib.metadata
import json
import io
import math
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def accumulate_batch(steps, proposals_this_batch: int) -> tuple[int, int]:
    """Count Niya's binary step cache, excluding its dummy starting index.

    The supported adapter contract returns exactly proposals + 1 entries and
    a false entry at index zero. Reject other layouts instead of guessing.
    """
    if isinstance(proposals_this_batch, bool) or not isinstance(proposals_this_batch, int) or proposals_this_batch < 1:
        raise ValueError("proposals_this_batch must be a positive integer")
    steps = np.asarray(steps)
    if steps.ndim != 1 or steps.size != proposals_this_batch + 1:
        raise ValueError("steps must have proposals_this_batch + 1 entries")
    if not np.all((steps == 0) | (steps == 1)) or steps[0] != 0:
        raise ValueError("steps must be binary with a false starting entry")
    return int(np.sum(steps[1:])), proposals_this_batch


def running_accept(accepted_total: int, attempted_total: int) -> float:
    if not 0 <= accepted_total <= attempted_total:
        raise ValueError("counts must satisfy 0 <= accepted <= attempted")
    return accepted_total / attempted_total if attempted_total else 0.0


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def load_config(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read once so the fingerprint hashes the exact configuration used."""
    raw = path.read_bytes()
    config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise ValueError("configuration must be a YAML mapping")
    return config, raw


def _validated_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize defaults and refuse settings that would mislabel the run."""
    defaults = {
        "experiment": {"name": "single_chain_cold_baseline", "seed": 1234},
        "science": {
            "problem": "synthetic",
            "backend": "cpu",
            "config": None,
            "rows": 24,
            "cols": 24,
            "resolution": 500.0,
            "data_dir": "MCMC_implementation/data",
            "sigma_mc": 3.0,
        },
        "sampling": {"temperature": 1.0, "batch_n_iterations": 51,
                     "num_batches": 40, "budget_mode": "proposals"},
        "logging": {"terminal": True, "log_every_batches": 1},
        "runtime": {"output_dir": "results/single_chain_cold_baseline"},
    }
    unknown = set(config) - set(defaults)
    if unknown:
        raise ValueError(f"unknown configuration sections: {sorted(unknown)}")
    resolved = {}
    for section, values in defaults.items():
        supplied = config.get(section, {})
        if not isinstance(supplied, dict):
            raise ValueError(f"{section} must be a mapping")
        allowed = set(values) | ({"rng_seed", "rf_seed"} if section == "experiment" else set())
        if set(supplied) - allowed:
            raise ValueError(f"unknown {section} settings: {sorted(set(supplied) - allowed)}")
        resolved[section] = {**values, **supplied}
    exp, science, sampling = (resolved[k] for k in ("experiment", "science", "sampling"))
    seed = _integer(exp["seed"], "experiment.seed")
    exp["rng_seed"] = _integer(exp.get("rng_seed", seed), "experiment.rng_seed")
    exp["rf_seed"] = _integer(exp.get("rf_seed", seed + 1), "experiment.rf_seed")
    if not isinstance(exp["name"], str) or not exp["name"].strip():
        raise ValueError("experiment.name must be a nonempty string")
    if science["backend"] not in ("cpu", "cuda"):
        raise ValueError("science.backend must be cpu or cuda")
    if science["backend"] == "cuda":
        raise ValueError("CUDA baseline is not wired to the adapter yet; use backend: cpu")
    if science["problem"] not in ("synthetic", "stancomb"):
        raise ValueError("science.problem must be synthetic or stancomb")
    if science["config"] is not None:
        raise ValueError("science.config must be null for the shipped builders")
    if not isinstance(science["data_dir"], str) or not science["data_dir"].strip():
        raise ValueError("science.data_dir must be a nonempty path")
    sigma_mc = science["sigma_mc"]
    if isinstance(sigma_mc, bool) or not isinstance(sigma_mc, (int, float)) or not math.isfinite(sigma_mc) or sigma_mc <= 0:
        raise ValueError("science.sigma_mc must be a positive finite number")
    science["sigma_mc"] = float(sigma_mc)
    if science["problem"] == "synthetic":
        for axis in ("rows", "cols"):
            _integer(science[axis], f"science.{axis}", 8)
        resolution = science["resolution"]
        if isinstance(resolution, bool) or not isinstance(resolution, (int, float)) or not math.isfinite(resolution) or resolution <= 0:
            raise ValueError("science.resolution must be positive and finite")
    temperature = sampling["temperature"]
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or temperature != 1.0:
        raise ValueError("single-chain cold baseline requires sampling.temperature: 1.0")
    _integer(sampling["batch_n_iterations"], "sampling.batch_n_iterations", 2)
    _integer(sampling["num_batches"], "sampling.num_batches", 1)
    if sampling["budget_mode"] != "proposals":
        raise ValueError("only budget_mode: proposals is implemented")
    if not isinstance(resolved["logging"]["terminal"], bool):
        raise ValueError("logging.terminal must be a boolean")
    _integer(resolved["logging"]["log_every_batches"], "logging.log_every_batches", 1)
    output = resolved["runtime"]["output_dir"]
    if not isinstance(output, str) or not output.strip():
        raise ValueError("runtime.output_dir must be a nonempty path")
    return resolved


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args], stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_fingerprint(config, adapter, config_path: Path, config_bytes: bytes) -> dict[str, Any]:
    from adapters import spectral_rng_overlay, topography_mcmc_adapter
    from gstatsMCMC import MCMC, Topography

    modules = (topography_mcmc_adapter, spectral_rng_overlay, MCMC, Topography,
               sys.modules[__name__])
    sources = {}
    for module in modules:
        path = Path(module.__file__).resolve()
        sources[module.__name__] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    packages = {}
    for name in ("numpy", "scipy", "numba", "gstools", "gstatsim", "scikit-gstat", "PyYAML"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "unknown"
    meta = adapter.get_metadata()
    return {
        "experiment_name": config["experiment"]["name"],
        "backend": config["science"]["backend"], "problem": config["science"]["problem"],
        "temperature": 1.0, "exchange": False, **config["experiment"],
        **config["sampling"], "bed_shape": list(meta["bed_shape"]), "bed_dtype": meta["bed_dtype"],
        "git_rev": _git_output("rev-parse", "HEAD"),
        "git_status": _git_output("status", "--porcelain", "--untracked-files=normal"),
        "hostname": socket.gethostname(), "platform": platform.platform(),
        "python_version": platform.python_version(), "python_executable": sys.executable,
        "config_path": str(config_path.resolve()),
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "resolved_config": config, "package_versions": packages, "sources": sources,
        "rng_policy": "chain Generator + RF Generator; existing spectral_rng_overlay uses RF.rng",
    }


def run_baseline(config_path: Path | str, *, output_dir: Path | str | None = None) -> dict[str, Any]:
    config_path = Path(config_path)
    supplied, raw = load_config(config_path)
    config = _validated_config(supplied)
    # Relative output paths are anchored to the repository, independent of cwd.
    if output_dir is not None:
        config["runtime"]["output_dir"] = str(output_dir)
    output = Path(config["runtime"]["output_dir"])
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    from adapters.stancomb_crf import build_stancomb_crf_pair
    from adapters.topography_mcmc_adapter import TopographyMCMCAdapter, build_synthetic_crf_pair

    exp, science, sampling, logging = (config[k] for k in ("experiment", "science", "sampling", "logging"))
    # Both proposal RNG streams are explicit; no global seed is needed.
    # The scientific constructors print usage instructions unconditionally.
    # Keep the CLI output limited to the stable benchmark metrics lines.
    with redirect_stdout(io.StringIO()):
        if science["problem"] == "synthetic":
            chain, rf = build_synthetic_crf_pair(
                rows=science["rows"],
                cols=science["cols"],
                resolution=science["resolution"],
                chain_seed=exp["rng_seed"],
                rf_seed=exp["rf_seed"],
            )
        else:
            chain, rf = build_stancomb_crf_pair(
                data_dir=science["data_dir"],
                sigma_mc=science["sigma_mc"],
                chain_seed=exp["rng_seed"],
                rf_seed=exp["rf_seed"],
            )
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=exp["rng_seed"], temperature=1.0)
    fingerprint = build_fingerprint(config, adapter, config_path, raw)
    fingerprint_json = json.dumps(fingerprint, sort_keys=True, allow_nan=False)
    fingerprint_id = hashlib.sha256(fingerprint_json.encode()).hexdigest()
    (output / "fingerprint.json").write_text(fingerprint_json + "\n")

    accepted = attempted = 0
    n = sampling["batch_n_iterations"]
    batches = sampling["num_batches"]
    with (output / "batch_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "batch", "accepted_delta", "attempted_delta", "accepted", "attempted",
            "a_local", "energy", "batch_wall_s", "wall_s", "proposals_per_second",
        ])
        writer.writeheader()
        # Initialization, fingerprinting, and final output serialization are excluded.
        start = time.perf_counter()
        for batch in range(1, batches + 1):
            batch_start = time.perf_counter()
            result = adapter.run_batch(n)
            batch_end = time.perf_counter()
            proposals = result["proposals_this_batch"]
            if proposals != n - 1:
                raise ValueError("adapter violated run(n) == n - 1 proposals contract")
            accepted_delta, attempted_delta = accumulate_batch(result["steps"], proposals)
            accepted += accepted_delta
            attempted += attempted_delta
            energy = float(result["energy"])
            if not math.isfinite(energy):
                raise ValueError("adapter returned nonfinite energy")
            wall_s = batch_end - start
            rate = attempted / wall_s
            row = dict(batch=batch, accepted_delta=accepted_delta, attempted_delta=attempted_delta,
                       accepted=accepted, attempted=attempted, a_local=running_accept(accepted, attempted),
                       energy=energy, batch_wall_s=batch_end - batch_start,
                       wall_s=wall_s, proposals_per_second=rate)
            writer.writerow(row)
            if logging["terminal"] and (batch % logging["log_every_batches"] == 0 or batch == batches):
                print(f"batch={batch}/{batches}  proposals={attempted}  a_local={row['a_local']:.4f}  "
                      f"E={energy:.6e}  propos/s={rate:.1f}  wall_s={wall_s:.3f}  "
                      f"batch_wall_s={row['batch_wall_s']:.3f}", flush=True)
    summary = {
        "accepted": accepted, "attempted": attempted, "a_local": running_accept(accepted, attempted),
        "energy_final": energy, "wall_s": wall_s, "proposals_per_second": rate,
        "budget_mode": "proposals", "batches_completed": batches,
        "fingerprint_id": fingerprint_id, "fingerprint": fingerprint,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    if logging["terminal"]:
        print(f"BASELINE DONE  proposals={attempted}  a_local={summary['a_local']:.4f}  "
              f"E_final={energy:.6e}  wall_s={wall_s:.3f}  propos/s={rate:.1f}  "
              f"fingerprint={fingerprint_id}", flush=True)
    return summary
