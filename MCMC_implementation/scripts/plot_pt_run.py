#!/usr/bin/env python3
"""Standardized PT-enabled run metrics figure.

Mirrors the dual-cold layout (energy, local accept, time) and adds a
parallel-tempering panel: swap probability, cumulative a_swap, and T labels.
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
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# Shared with dual-cold figure styling
C0 = "#1f77b4"
C1 = "#ff7f0e"
C_COORD = "#2ca02c"
C_SWAP = "0.35"
C_COLD = "#2ca02c"


def _parse_list(cell: str) -> list[float]:
    value = ast.literal_eval(cell)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"expected length-2 list, got {cell!r}")
    return [float(value[0]), float(value[1])]


def load_pt_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    metrics_path = run_dir / "round_metrics.csv"
    summary_path = run_dir / "summary.json"
    if not metrics_path.is_file():
        raise FileNotFoundError(metrics_path)
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)

    summary = json.loads(summary_path.read_text())
    if summary.get("exchange_enabled") is not True:
        raise ValueError("refusing to plot: exchange_enabled must be true for PT")

    rounds: list[int] = []
    e0: list[float] = []
    e1: list[float] = []
    e_cold: list[float] = []
    a0: list[float] = []
    a1: list[float] = []
    ac0: list[float] = []
    ac1: list[float] = []
    t0: list[float] = []
    t1: list[float] = []
    t_coord: list[float] = []
    temps0: list[float] = []
    temps1: list[float] = []
    p_swap: list[float] = []
    accepted: list[bool] = []
    cold_idx: list[int] = []

    with metrics_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rounds.append(int(row["round"]))
            energies = _parse_list(row["E"])
            accepts = _parse_list(row["a_local"])
            accepts_c = _parse_list(row["a_local_cumulative"])
            compute = _parse_list(row["t_compute_ms"])
            temps = _parse_list(row["T"])
            e0.append(energies[0])
            e1.append(energies[1])
            a0.append(accepts[0])
            a1.append(accepts[1])
            ac0.append(accepts_c[0])
            ac1.append(accepts_c[1])
            t0.append(compute[0])
            t1.append(compute[1])
            t_coord.append(float(row["t_coord_ms"]))
            temps0.append(temps[0])
            temps1.append(temps[1])
            if row.get("p_swap") in (None, ""):
                p_swap.append(0.0)
            else:
                p_swap.append(float(row["p_swap"]))
            accepted.append(str(row.get("accepted", "")).lower() in {"true", "1"})
            if row.get("cold_worker") not in (None, ""):
                ci = int(float(row["cold_worker"]))
            else:
                ci = 0 if abs(temps[0] - 1.0) < 1e-9 else 1
            cold_idx.append(ci)
            e_cold.append(energies[ci])

    if not rounds:
        raise ValueError("round_metrics.csv has no rows")

    swap_rounds = [r for r, ok in zip(rounds, accepted) if ok]
    a_swap_cum = []
    n_acc = 0
    for i, ok in enumerate(accepted):
        if ok:
            n_acc += 1
        a_swap_cum.append(n_acc / float(i + 1))

    return {
        "run_dir": run_dir,
        "summary": summary,
        "rounds": rounds,
        "E0": e0,
        "E1": e1,
        "E_cold": e_cold,
        "a0": a0,
        "a1": a1,
        "ac0": ac0,
        "ac1": ac1,
        "t0": t0,
        "t1": t1,
        "t_coord": t_coord,
        "T0": temps0,
        "T1": temps1,
        "p_swap": p_swap,
        "accepted": accepted,
        "swap_rounds": swap_rounds,
        "a_swap_cum": a_swap_cum,
        "cold_idx": cold_idx,
    }


def _mark_swaps(ax: Any, swap_rounds: list[int], *, label_once: bool = False) -> None:
    labeled = False
    for s in swap_rounds:
        kw: dict[str, Any] = {"color": C_SWAP, "ls": "--", "lw": 1.0, "alpha": 0.75}
        if label_once and not labeled:
            kw["label"] = "accepted swap"
            labeled = True
        ax.axvline(s, **kw)


def plot_pt(run: dict[str, Any], output_dir: Path, stem: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rounds = run["rounds"]
    summary = run["summary"]
    science = summary.get("science") or {}
    cfg = (summary.get("resolved_config") or {}).get("sampling") or {}
    props_per = int(cfg.get("batch_n_iterations", 0)) - 1
    n_rounds = len(rounds)
    temps = summary.get("temperatures_initial") or []
    a_swap = summary.get("a_swap")
    accepts = summary.get("swap_accepts")
    attempts = summary.get("swap_attempts")
    swap_rounds = run["swap_rounds"]

    fig, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True, constrained_layout=True)

    # --- Panel 1: Energy (standardized) + PT cold label + swap lines ---
    ax = axes[0]
    ax.plot(rounds, run["E0"], label="worker 0", color=C0, lw=1.6)
    ax.plot(rounds, run["E1"], label="worker 1", color=C1, lw=1.6)
    ax.plot(rounds, run["E_cold"], label="cold label (T=1)", color=C_COLD, lw=2.0, alpha=0.9)
    _mark_swaps(ax, swap_rounds, label_once=True)
    ax.set_ylabel("Energy E")
    ax.set_title(
        f"PT Stancomb — temperatures {temps}  |  exchange ON  |  "
        f"a_swap={a_swap} ({accepts}/{attempts})"
    )
    ax.legend(loc="best", frameon=False, fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # --- Panel 2: Local acceptance (same as dual-cold) ---
    ax = axes[1]
    ax.plot(rounds, run["a0"], label="worker 0 batch a_local", color=C0, alpha=0.85)
    ax.plot(rounds, run["a1"], label="worker 1 batch a_local", color=C1, alpha=0.85)
    ax.plot(rounds, run["ac0"], label="worker 0 cumulative", color=C0, ls="--", lw=1.2)
    ax.plot(rounds, run["ac1"], label="worker 1 cumulative", color=C1, ls="--", lw=1.2)
    ax.axhline(0.5, color="0.5", ls=":", lw=1, label="0.5 reference")
    _mark_swaps(ax, swap_rounds)
    ax.set_ylabel("Local accept rate")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="best", fontsize=8, frameon=False, ncol=2)
    ax.grid(True, alpha=0.3)

    # --- Panel 3: Parallel tempering details ---
    ax = axes[2]
    p = np.asarray(run["p_swap"], dtype=float)
    # floor for log-scale visibility of near-zero proposals
    p_plot = np.clip(p, 1e-300, 1.0)
    ax.semilogy(rounds, p_plot, color="#9467bd", lw=1.2, alpha=0.9, label="p_swap")
    ax.axhline(1.0, color="0.6", ls=":", lw=0.8)
    if swap_rounds:
        ax.scatter(
            swap_rounds,
            [max(run["p_swap"][rounds.index(s)], 1e-300) for s in swap_rounds],
            color="#d62728",
            s=36,
            zorder=5,
            label="accepted swap",
        )
    ax.set_ylabel("p_swap (log)")
    ax.set_ylim(1e-120, 3.0)
    ax.grid(True, alpha=0.3, which="both")

    ax_r = ax.twinx()
    ax_r.plot(rounds, run["a_swap_cum"], color="#8c564b", lw=1.8, label="cumulative a_swap")
    ax_r.step(rounds, run["T0"], where="post", color=C0, ls=":", lw=1.2, alpha=0.85, label="T worker 0")
    ax_r.step(rounds, run["T1"], where="post", color=C1, ls=":", lw=1.2, alpha=0.85, label="T worker 1")
    ax_r.set_ylabel("a_swap cum / T")
    ax_r.set_ylim(0.0, max(temps + [1.5]) + 0.5)

    lines_l, labels_l = ax.get_legend_handles_labels()
    lines_r, labels_r = ax_r.get_legend_handles_labels()
    ax.legend(lines_l + lines_r, labels_l + labels_r, loc="best", fontsize=7, frameon=False, ncol=3)
    ax.set_title(
        f"Parallel tempering — swap attempts every round  |  "
        f"accepts={accepts}/{attempts}"
    )

    # --- Panel 4: Time (same as dual-cold) ---
    ax = axes[3]
    ax.plot(rounds, run["t0"], label="worker 0 compute", color=C0, lw=1.2)
    ax.plot(rounds, run["t1"], label="worker 1 compute", color=C1, lw=1.2)
    ax.plot(rounds, run["t_coord"], label="coordinator round", color=C_COORD, lw=1.2, alpha=0.8)
    _mark_swaps(ax, swap_rounds)
    ax.set_xlabel("Round")
    ax.set_ylabel("Time (ms)")
    ax.legend(loc="best", frameon=False, fontsize=8)
    ax.grid(True, alpha=0.3)

    bed = science.get("bed_shape")
    fig.supxlabel(
        f"problem={science.get('problem')}  bed={bed}  "
        f"rounds={n_rounds}  ~{props_per} proposals/round/worker  "
        f"temps={temps}  swap_attempts={attempts}  a_swap={a_swap}",
        fontsize=9,
    )

    out = output_dir / f"{stem}_trace.png"
    fig.savefig(out, dpi=160)
    fig.savefig(output_dir / f"{stem}_trace.pdf")
    plt.close(fig)

    meta = {
        "source_run": str(run["run_dir"]),
        "figure_png": str(out),
        "rounds": n_rounds,
        "temperatures_initial": temps,
        "a_swap": a_swap,
        "swap_accepts": accepts,
        "swap_attempts": attempts,
        "swap_rounds": swap_rounds,
        "E0_start": run["E0"][0],
        "E0_end": run["E0"][-1],
        "E1_start": run["E1"][0],
        "E1_end": run["E1"][-1],
        "E_cold_end": run["E_cold"][-1],
        "a_local_cumulative_final": [run["ac0"][-1], run["ac1"][-1]],
        "caption": (
            "Stancomb PT run with temperature exchange enabled. "
            "Panels match dual-cold (energy, local accept, time) plus a PT panel "
            "for p_swap, cumulative a_swap, and per-worker temperatures."
        ),
    }
    (output_dir / f"{stem}_summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "two_replica_stancomb_pt_r200",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "figures" / "pt_stancomb_r200",
    )
    parser.add_argument("--stem", type=str, default="pt_stancomb_r200")
    args = parser.parse_args()
    run = load_pt_run(args.run_dir)
    out = plot_pt(run, args.output_dir, args.stem)
    print(f"wrote {out}")
    print(
        f"a_swap={run['summary'].get('a_swap')}  "
        f"accepts={run['summary'].get('swap_accepts')}/"
        f"{run['summary'].get('swap_attempts')}"
    )


if __name__ == "__main__":
    main()
