"""Plot single-chain cold baseline diagnostics from an archived run directory."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REQUIRED_COLUMNS = (
    "batch",
    "attempted",
    "a_local",
    "energy",
    "wall_s",
    "proposals_per_second",
    "batch_wall_s",
)

CAPTION = (
    "Stancomb–Wills 500×500 CRF cold chain (T=1), short Metropolis smoke. "
    "Not an equal-resource dual-cold baseline and not a PT comparison."
)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _load_batch_metrics(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("batch_metrics.csv has no header")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"batch_metrics.csv missing columns: {missing}")
        rows: list[dict[str, float]] = []
        for raw in reader:
            rows.append({key: float(raw[key]) for key in REQUIRED_COLUMNS})
    if not rows:
        raise ValueError("batch_metrics.csv has no data rows")
    return rows


def load_run(run_dir: Path) -> dict[str, Any]:
    """Load and validate a single-chain baseline archive."""
    run_dir = run_dir.resolve()
    metrics_path = run_dir / "batch_metrics.csv"
    summary_path = run_dir / "summary.json"
    fingerprint_path = run_dir / "fingerprint.json"
    for path in (metrics_path, summary_path, fingerprint_path):
        if not path.is_file():
            raise FileNotFoundError(f"missing required file: {path}")

    rows = _load_batch_metrics(metrics_path)
    summary = _load_json(summary_path)
    fingerprint = _load_json(fingerprint_path)

    problem = fingerprint.get("problem")
    if problem != "stancomb":
        raise ValueError(
            f"refusing to plot: fingerprint.problem={problem!r} (expected 'stancomb')"
        )
    temperature = float(fingerprint.get("temperature", -1.0))
    if temperature != 1.0:
        raise ValueError(f"refusing to plot: temperature={temperature} (expected 1.0)")

    return {
        "run_dir": run_dir,
        "rows": rows,
        "summary": summary,
        "fingerprint": fingerprint,
        "fingerprint_id": summary.get("fingerprint_id") or fingerprint.get("fingerprint_id"),
    }


def _series(rows: list[dict[str, float]], key: str) -> list[float]:
    return [row[key] for row in rows]


def _style_axes(ax: plt.Axes, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_energy(rows: list[dict[str, float]], *, title: str, output: Path) -> Path:
    attempted = _series(rows, "attempted")
    energy = _series(rows, "energy")
    fig, ax = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    ax.plot(attempted, energy, color="#1f4e79", linewidth=2.0, marker="o", markersize=4)
    ax.annotate(
        f"start {energy[0]:.3e}",
        xy=(attempted[0], energy[0]),
        xytext=(8, 8),
        textcoords="offset points",
        fontsize=8,
    )
    ax.annotate(
        f"end {energy[-1]:.3e}",
        xy=(attempted[-1], energy[-1]),
        xytext=(-70, -14),
        textcoords="offset points",
        fontsize=8,
    )
    _style_axes(ax, title, "Cumulative proposals", "Energy E")
    fig.text(0.01, 0.01, CAPTION, fontsize=7, color="#333333", wrap=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)
    return output


def plot_accept(rows: list[dict[str, float]], *, title: str, final_a_local: float, output: Path) -> Path:
    attempted = _series(rows, "attempted")
    a_local = _series(rows, "a_local")
    fig, ax = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    ax.plot(attempted, a_local, color="#0b6e4f", linewidth=2.0, marker="o", markersize=4)
    ax.axhline(final_a_local, color="#666666", linestyle="--", linewidth=1.0, label=f"final={final_a_local:.3f}")
    ax.set_ylim(0.0, 1.0)
    ax.legend(frameon=False, loc="best")
    _style_axes(ax, title, "Cumulative proposals", r"Running $a_{\mathrm{local}}$")
    fig.text(0.01, 0.01, CAPTION, fontsize=7, color="#333333", wrap=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)
    return output


def plot_throughput(rows: list[dict[str, float]], *, title: str, output: Path) -> Path:
    attempted = _series(rows, "attempted")
    rate = _series(rows, "proposals_per_second")
    fig, ax = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    ax.plot(attempted, rate, color="#8b4513", linewidth=2.0, marker="o", markersize=4)
    _style_axes(
        ax,
        title + " (systems diagnostic)",
        "Cumulative proposals",
        "Proposals / second",
    )
    fig.text(0.01, 0.01, CAPTION, fontsize=7, color="#333333", wrap=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)
    return output


def render_run(run_dir: Path, output_dir: Path, *, prefix: str = "stancomb_single_cold") -> dict[str, Any]:
    """Load a run archive and write energy / accept / throughput figures."""
    output_dir = output_dir.resolve()
    if output_dir.name == "figures" and (output_dir.parent / "MCMC_implementation").is_dir():
        pass  # repo-root figures/ is expected
    banned = output_dir.resolve()
    if banned.as_posix().endswith("/MCMC_implementation/figures"):
        raise ValueError("refusing to write into MCMC_implementation/figures (Bakari assets)")

    payload = load_run(run_dir)
    rows = payload["rows"]
    summary = payload["summary"]
    fingerprint = payload["fingerprint"]
    bed_shape = fingerprint.get("bed_shape")
    title = (
        f"Stancomb single-chain cold baseline  "
        f"bed={bed_shape}  T={fingerprint.get('temperature')}  "
        f"proposals={int(summary.get('attempted', rows[-1]['attempted']))}"
    )
    final_a = float(summary.get("a_local", rows[-1]["a_local"]))

    energy_path = plot_energy(rows, title=title, output=output_dir / f"{prefix}_energy.png")
    accept_path = plot_accept(
        rows, title=title, final_a_local=final_a, output=output_dir / f"{prefix}_accept.png"
    )
    throughput_path = plot_throughput(
        rows, title=title, output=output_dir / f"{prefix}_throughput.png"
    )

    manifest = {
        "run_dir": str(payload["run_dir"]),
        "output_dir": str(output_dir),
        "fingerprint_id": payload["fingerprint_id"],
        "problem": fingerprint.get("problem"),
        "bed_shape": bed_shape,
        "temperature": fingerprint.get("temperature"),
        "attempted": summary.get("attempted"),
        "a_local": summary.get("a_local"),
        "energy_final": summary.get("energy_final"),
        "wall_s": summary.get("wall_s"),
        "caption": CAPTION,
        "figures": {
            "energy_png": str(energy_path),
            "energy_pdf": str(energy_path.with_suffix(".pdf")),
            "accept_png": str(accept_path),
            "accept_pdf": str(accept_path.with_suffix(".pdf")),
            "throughput_png": str(throughput_path),
            "throughput_pdf": str(throughput_path.with_suffix(".pdf")),
        },
    }
    manifest_path = output_dir / f"{prefix}_summary.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
