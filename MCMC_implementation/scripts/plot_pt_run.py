#!/usr/bin/env python3
"""Standardized PT-enabled run metrics figure.

Mirrors the dual-cold layout (energy, local accept, time) and adds a
parallel-tempering panel: swap probability, cumulative / windowed a_swap, T.
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


def _rolling_mean(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return list(values)
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        chunk = values[lo : i + 1]
        out.append(sum(chunk) / float(len(chunk)))
    return out


def _count_round_trips(cold_idx: list[int]) -> int:
    """Count cold-label flips (proxy for temperature round-trips with 2 replicas)."""
    if len(cold_idx) < 2:
        return 0
    return sum(1 for a, b in zip(cold_idx, cold_idx[1:]) if a != b)


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
    a_swap_cum: list[float] = []
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


def _post_burnin_stats(
    run: dict[str, Any], burnin_round: int
) -> dict[str, Any]:
    rounds = run["rounds"]
    accepted = run["accepted"]
    cold_idx = run["cold_idx"]
    idx = [i for i, r in enumerate(rounds) if r >= burnin_round]
    if not idx:
        return {
            "burnin_round": burnin_round,
            "n": 0,
            "a_swap": None,
            "swap_accepts": 0,
            "round_trips": 0,
        }
    acc = [accepted[i] for i in idx]
    cold = [cold_idx[i] for i in idx]
    n_acc = sum(1 for x in acc if x)
    return {
        "burnin_round": burnin_round,
        "n": len(idx),
        "a_swap": n_acc / float(len(idx)),
        "swap_accepts": n_acc,
        "round_trips": _count_round_trips(cold),
    }


def _mark_swaps(ax: Any, swap_rounds: list[int], *, label_once: bool = False) -> None:
    """Draw swap markers only when sparse; otherwise one onset line."""
    if not swap_rounds:
        return
    if len(swap_rounds) > 40:
        ax.axvline(
            swap_rounds[0],
            color=C_SWAP,
            ls="--",
            lw=1.2,
            alpha=0.85,
            label="first accepted swap" if label_once else None,
        )
        return
    labeled = False
    for s in swap_rounds:
        kw: dict[str, Any] = {"color": C_SWAP, "ls": "--", "lw": 1.0, "alpha": 0.75}
        if label_once and not labeled:
            kw["label"] = "accepted swap"
            labeled = True
        ax.axvline(s, **kw)


def plot_pt(
    run: dict[str, Any],
    output_dir: Path,
    stem: str,
    *,
    burnin_round: int = 180,
) -> Path:
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
    post = _post_burnin_stats(run, burnin_round)
    round_trips_all = _count_round_trips(run["cold_idx"])
    a_swap_win = _rolling_mean([1.0 if x else 0.0 for x in run["accepted"]], 20)

    fig, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True, constrained_layout=True)

    # --- Panel 1: Energy ---
    ax = axes[0]
    ax.plot(rounds, run["E0"], label="worker 0", color=C0, lw=1.6)
    ax.plot(rounds, run["E1"], label="worker 1", color=C1, lw=1.6)
    ax.plot(rounds, run["E_cold"], label="cold label (T=1)", color=C_COLD, lw=2.0, alpha=0.9)
    if post["n"]:
        ax.axvspan(burnin_round, rounds[-1], color="0.85", alpha=0.35, label="post-burn-in")
    _mark_swaps(ax, swap_rounds, label_once=True)
    ax.set_ylabel("Energy E")
    a_post = post["a_swap"]
    a_post_s = f"{a_post:.3f}" if a_post is not None else "n/a"
    ax.set_title(
        f"PT Stancomb — temps {temps}  |  exchange ON  |  "
        f"a_swap={a_swap:.3f} ({accepts}/{attempts})  |  "
        f"post≥{burnin_round} a_swap={a_post_s}"
    )
    ax.legend(loc="best", frameon=False, fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    # --- Panel 2: Local acceptance ---
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

    # --- Panel 3: Parallel tempering ---
    ax = axes[2]
    ax.plot(rounds, run["p_swap"], color="#9467bd", lw=1.1, alpha=0.85, label="p_swap")
    ax.plot(rounds, a_swap_win, color="#d62728", lw=1.6, label="a_swap window20")
    ax.plot(rounds, run["a_swap_cum"], color="#8c564b", lw=1.6, label="a_swap cumulative")
    ax.axhline(0.234, color="0.4", ls=":", lw=1.0, label="0.234 target")
    if post["n"]:
        ax.axvspan(burnin_round, rounds[-1], color="0.85", alpha=0.35)
    ax.set_ylabel("Swap metrics")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)

    ax_t = ax.twinx()
    ax_t.step(rounds, run["T0"], where="post", color=C0, ls=":", lw=1.3, alpha=0.9, label="T worker 0")
    ax_t.step(rounds, run["T1"], where="post", color=C1, ls=":", lw=1.3, alpha=0.9, label="T worker 1")
    ax_t.set_ylabel("Temperature T")
    t_hi = max(temps + [1.01]) + 0.02
    ax_t.set_ylim(min(temps + [1.0]) - 0.02, t_hi)

    lines_l, labels_l = ax.get_legend_handles_labels()
    lines_r, labels_r = ax_t.get_legend_handles_labels()
    ax.legend(lines_l + lines_r, labels_l + labels_r, loc="best", fontsize=7, frameon=False, ncol=3)
    ax.set_title(
        f"Parallel tempering — accepts={accepts}/{attempts}  |  "
        f"cold flips={round_trips_all}  |  "
        f"post≥{burnin_round} flips={post['round_trips']}"
    )

    # --- Panel 4: Time ---
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
        f"temps={temps}  a_swap={a_swap:.3f}  "
        f"post≥{burnin_round} a_swap={a_post_s}  "
        f"cold_flips={round_trips_all}",
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
        "cold_label_flips": round_trips_all,
        "post_burnin": post,
        "E0_start": run["E0"][0],
        "E0_end": run["E0"][-1],
        "E1_start": run["E1"][0],
        "E1_end": run["E1"][-1],
        "E_cold_end": run["E_cold"][-1],
        "a_local_cumulative_final": [run["ac0"][-1], run["ac1"][-1]],
        "caption": (
            "Stancomb PT run with temperature exchange enabled. "
            "Panels: energy (+ cold label), local accept, PT swap metrics "
            "(p_swap, windowed/cumulative a_swap, T), and wall time."
        ),
    }
    (output_dir / f"{stem}_summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "two_replica_stancomb_pt_r600_T1.01",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "figures" / "pt_stancomb_r600_T1.01",
    )
    parser.add_argument("--stem", type=str, default="pt_stancomb_r600_T1.01")
    parser.add_argument(
        "--burnin-round",
        type=int,
        default=180,
        help="Round after which post-burn-in a_swap / flips are reported",
    )
    args = parser.parse_args()
    run = load_pt_run(args.run_dir)
    out = plot_pt(run, args.output_dir, args.stem, burnin_round=args.burnin_round)
    post = _post_burnin_stats(run, args.burnin_round)
    print(f"wrote {out}")
    print(
        f"a_swap={run['summary'].get('a_swap')}  "
        f"accepts={run['summary'].get('swap_accepts')}/"
        f"{run['summary'].get('swap_attempts')}  "
        f"cold_flips={_count_round_trips(run['cold_idx'])}  "
        f"post>={args.burnin_round} a_swap={post['a_swap']} "
        f"flips={post['round_trips']}"
    )


if __name__ == "__main__":
    main()
