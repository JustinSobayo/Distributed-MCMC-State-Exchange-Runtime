#!/usr/bin/env python3
"""Plot dual-cold (two independent T=1 chains) round metrics.

This is the equal-resource control visualization — not a PT comparison.
When a PT archive exists, use the energy-trace plotter from the figures plan.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_list(cell: str) -> list[float]:
    value = ast.literal_eval(cell)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"expected length-2 list, got {cell!r}")
    return [float(value[0]), float(value[1])]


def load_dual_cold_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    metrics_path = run_dir / "round_metrics.csv"
    summary_path = run_dir / "summary.json"
    if not metrics_path.is_file():
        raise FileNotFoundError(metrics_path)
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)

    summary = json.loads(summary_path.read_text())
    if summary.get("exchange_enabled") is not False:
        raise ValueError("refusing to plot: exchange_enabled must be false for dual-cold")
    temps = summary.get("temperatures_initial") or []
    if list(temps) != [1.0, 1.0]:
        raise ValueError(f"refusing to plot: temperatures_initial={temps!r} (expected [1,1])")

    rounds: list[int] = []
    e0: list[float] = []
    e1: list[float] = []
    a0: list[float] = []
    a1: list[float] = []
    ac0: list[float] = []
    ac1: list[float] = []
    t0: list[float] = []
    t1: list[float] = []
    t_coord: list[float] = []

    with metrics_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rounds.append(int(row["round"]))
            energies = _parse_list(row["E"])
            accepts = _parse_list(row["a_local"])
            accepts_c = _parse_list(row["a_local_cumulative"])
            compute = _parse_list(row["t_compute_ms"])
            e0.append(energies[0])
            e1.append(energies[1])
            a0.append(accepts[0])
            a1.append(accepts[1])
            ac0.append(accepts_c[0])
            ac1.append(accepts_c[1])
            t0.append(compute[0])
            t1.append(compute[1])
            t_coord.append(float(row["t_coord_ms"]))

    if not rounds:
        raise ValueError("round_metrics.csv has no rows")

    return {
        "run_dir": run_dir,
        "summary": summary,
        "rounds": rounds,
        "E0": e0,
        "E1": e1,
        "a0": a0,
        "a1": a1,
        "ac0": ac0,
        "ac1": ac1,
        "t0": t0,
        "t1": t1,
        "t_coord": t_coord,
    }


def plot_dual_cold(run: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rounds = run["rounds"]
    summary = run["summary"]
    science = summary.get("science") or {}
    cfg = (summary.get("resolved_config") or {}).get("sampling") or {}
    props_per = int(cfg.get("batch_n_iterations", 0)) - 1
    n_rounds = len(rounds)

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, constrained_layout=True)

    ax = axes[0]
    ax.plot(rounds, run["E0"], label="worker 0 (T=1)", color="#1f77b4", lw=1.6)
    ax.plot(rounds, run["E1"], label="worker 1 (T=1)", color="#ff7f0e", lw=1.6)
    ax.set_ylabel("Energy E")
    ax.set_title(
        "Dual-cold Stancomb — temperatures [1.0, 1.0]  |  exchange OFF  |  "
        f"a_swap=0 (0/{summary.get('swap_attempts', 0)})"
    )
    ax.legend(loc="best", frameon=False)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(rounds, run["a0"], label="worker 0 batch a_local", color="#1f77b4", alpha=0.85)
    ax.plot(rounds, run["a1"], label="worker 1 batch a_local", color="#ff7f0e", alpha=0.85)
    ax.plot(rounds, run["ac0"], label="worker 0 cumulative", color="#1f77b4", ls="--", lw=1.2)
    ax.plot(rounds, run["ac1"], label="worker 1 cumulative", color="#ff7f0e", ls="--", lw=1.2)
    ax.axhline(0.5, color="0.5", ls=":", lw=1, label="0.5 reference")
    ax.set_ylabel("Local accept rate")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="best", fontsize=8, frameon=False, ncol=2)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(rounds, run["t0"], label="worker 0 compute", color="#1f77b4", lw=1.2)
    ax.plot(rounds, run["t1"], label="worker 1 compute", color="#ff7f0e", lw=1.2)
    ax.plot(rounds, run["t_coord"], label="coordinator round", color="#2ca02c", lw=1.2, alpha=0.8)
    ax.set_xlabel("Round")
    ax.set_ylabel("Time (ms)")
    ax.legend(loc="best", frameon=False, fontsize=8)
    ax.grid(True, alpha=0.3)

    bed = science.get("bed_shape")
    fig.supxlabel(
        f"problem={science.get('problem')}  bed={bed}  "
        f"rounds={n_rounds}  ~{props_per} proposals/round/worker  "
        f"swap_attempts={summary.get('swap_attempts')}  "
        "(equal-resource control; not PT)",
        fontsize=9,
    )

    out = output_dir / "dual_cold_stancomb_r200_trace.png"
    fig.savefig(out, dpi=160)
    fig.savefig(output_dir / "dual_cold_stancomb_r200_trace.pdf")
    plt.close(fig)

    meta = {
        "source_run": str(run["run_dir"]),
        "figure_png": str(out),
        "rounds": n_rounds,
        "E0_start": run["E0"][0],
        "E0_end": run["E0"][-1],
        "E1_start": run["E1"][0],
        "E1_end": run["E1"][-1],
        "a_local_cumulative_final": [run["ac0"][-1], run["ac1"][-1]],
        "caption": (
            "Two independent Stancomb CRF chains at T=1 with temperature exchange disabled. "
            "Use as the equal-resource baseline when a matched PT run is available."
        ),
    }
    (output_dir / "dual_cold_stancomb_r200_summary.json").write_text(
        json.dumps(meta, indent=2) + "\n"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "two_replica_stancomb_baseline_cold_r200",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "figures" / "dual_cold_stancomb_r200",
    )
    args = parser.parse_args()
    run = load_dual_cold_run(args.run_dir)
    out = plot_dual_cold(run, args.output_dir)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
