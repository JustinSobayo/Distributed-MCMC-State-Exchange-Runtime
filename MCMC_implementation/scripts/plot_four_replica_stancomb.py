#!/usr/bin/env python3
"""Visualize matched four-replica Stancomb dual-cold vs PT runs.

Reads round_metrics.json (variable replica count) + summary.json.
Writes multi-panel PNGs/PDFs under figures/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKER_COLORS = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b")
COLD_COLOR = "#111111"
SWAP_COLOR = "0.35"


def _rolling_mean(values: list[float], window: int) -> np.ndarray:
    if window <= 1:
        return np.asarray(values, dtype=float)
    out = np.empty(len(values), dtype=float)
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        out[i] = float(np.mean(values[lo : i + 1]))
    return out


def load_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    summary = json.loads((run_dir / "summary.json").read_text())
    rows = json.loads((run_dir / "round_metrics.json").read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"no rounds in {run_dir}")
    n_rep = int(summary.get("replicas") or len(rows[0]["E"]))
    rounds = [int(r["round"]) for r in rows]
    E = np.asarray([r["E"] for r in rows], dtype=float)
    T = np.asarray([r["T"] for r in rows], dtype=float)
    a_local = np.asarray([r["a_local"] for r in rows], dtype=float)
    a_cum = np.asarray([r["a_local_cumulative"] for r in rows], dtype=float)
    t_compute = np.asarray([r["t_compute_ms"] for r in rows], dtype=float)
    t_coord = np.asarray([r["t_coord_ms"] for r in rows], dtype=float)

    cold_idx: list[int | None] = []
    e_cold: list[float] = []
    for r, energies, temps in zip(rows, E, T):
        ci = r.get("cold_worker")
        if ci is None:
            matches = [i for i, t in enumerate(temps) if abs(float(t) - 1.0) < 1e-9]
            ci = int(matches[0]) if matches else 0
        else:
            ci = int(ci)
        cold_idx.append(ci)
        e_cold.append(float(energies[ci]))

    accepted_round = [bool(r.get("accepted")) for r in rows]
    swap_rounds = [rd for rd, ok in zip(rounds, accepted_round) if ok]

    # Per-edge accept indicators (PT only; empty when exchange off)
    edge_keys: list[str] = []
    edge_accept_series: dict[str, list[float]] = {}
    for r in rows:
        for s in r.get("swaps") or []:
            key = f"{int(s['i'])}-{int(s['j'])}"
            if key not in edge_accept_series:
                edge_keys.append(key)
                edge_accept_series[key] = [0.0] * len(rows)
    for i, r in enumerate(rows):
        for s in r.get("swaps") or []:
            key = f"{int(s['i'])}-{int(s['j'])}"
            if s.get("accepted"):
                edge_accept_series[key][i] = 1.0

    a_swap_cum: list[float] = []
    n_acc = 0
    for i, ok in enumerate(accepted_round):
        # For multi-edge rounds, summary uses swap_accepts over attempts;
        # round-level "accepted" means at least one edge accepted.
        if ok:
            n_acc += 1
        a_swap_cum.append(n_acc / float(i + 1))

    return {
        "run_dir": run_dir,
        "summary": summary,
        "n_replicas": n_rep,
        "rounds": rounds,
        "E": E,
        "T": T,
        "a_local": a_local,
        "a_cum": a_cum,
        "t_compute": t_compute,
        "t_coord": t_coord,
        "cold_idx": cold_idx,
        "E_cold": np.asarray(e_cold, dtype=float),
        "accepted_round": accepted_round,
        "swap_rounds": swap_rounds,
        "edge_keys": edge_keys,
        "edge_accept_series": edge_accept_series,
        "a_swap_cum_round": a_swap_cum,
    }


def _mark_swaps(ax: Any, swap_rounds: list[int]) -> None:
    if not swap_rounds:
        return
    if len(swap_rounds) > 60:
        ax.axvline(swap_rounds[0], color=SWAP_COLOR, ls="--", lw=1.2, alpha=0.85)
        return
    for s in swap_rounds:
        ax.axvline(s, color=SWAP_COLOR, ls="--", lw=0.8, alpha=0.45)


def plot_comparison(
    baseline: dict[str, Any],
    pt: dict[str, Any],
    output_dir: Path,
    stem: str,
    *,
    burnin_round: int = 400,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rounds_b = baseline["rounds"]
    rounds_p = pt["rounds"]
    n_rep = pt["n_replicas"]
    summary = pt["summary"]
    temps0 = summary.get("temperatures_initial") or []
    a_swap = summary.get("a_swap")
    accepts = summary.get("swap_accepts")
    attempts = summary.get("swap_attempts")
    by_edge = summary.get("a_swap_by_edge") or {}

    fig, axes = plt.subplots(5, 1, figsize=(11, 14), sharex=False, constrained_layout=True)

    # --- 1. Matched energy: PT cold vs each baseline worker ---
    ax = axes[0]
    for w in range(baseline["n_replicas"]):
        ax.plot(
            rounds_b,
            baseline["E"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.0,
            alpha=0.55,
            label=f"baseline w{w}",
        )
    ax.plot(
        rounds_p,
        pt["E_cold"],
        color=COLD_COLOR,
        lw=2.2,
        label="PT cold label (T=1)",
    )
    if rounds_p[-1] >= burnin_round:
        ax.axvspan(burnin_round, rounds_p[-1], color="0.85", alpha=0.35, label="post-burn-in")
    _mark_swaps(ax, pt["swap_rounds"])
    ax.set_ylabel("Energy E")
    ax.set_title(
        f"Four-replica Stancomb — PT cold vs 4×T=1 baseline  |  "
        f"temps={temps0}  |  a_swap={a_swap:.4f} ({accepts}/{attempts})"
    )
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=3)
    ax.grid(True, alpha=0.3)

    # --- 2. PT worker energies ---
    ax = axes[1]
    for w in range(n_rep):
        ax.plot(
            rounds_p,
            pt["E"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.2,
            label=f"worker {w}",
        )
    ax.plot(rounds_p, pt["E_cold"], color=COLD_COLOR, lw=2.0, alpha=0.9, label="cold label")
    _mark_swaps(ax, pt["swap_rounds"])
    ax.set_ylabel("Energy E")
    ax.set_title("PT — per-worker energy (dashed verticals = rounds with ≥1 accepted swap)")
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=3)
    ax.grid(True, alpha=0.3)

    # --- 3. Temperatures ---
    ax = axes[2]
    for w in range(n_rep):
        ax.step(
            rounds_p,
            pt["T"][:, w],
            where="post",
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.3,
            label=f"T worker {w}",
        )
    ax.set_ylabel("Temperature T")
    ax.set_title("PT — temperature assignment per worker (beds stay; temps swap)")
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=4)
    ax.grid(True, alpha=0.3)

    # --- 4. Swap metrics ---
    ax = axes[3]
    ax.plot(
        rounds_p,
        pt["a_swap_cum_round"],
        color="#8c564b",
        lw=1.6,
        label="fraction of rounds with ≥1 accept (cum)",
    )
    for key in pt["edge_keys"]:
        series = pt["edge_accept_series"][key]
        ax.plot(
            rounds_p,
            _rolling_mean(series, 50),
            lw=1.3,
            label=f"edge {key} accept window50 (a_swap={by_edge.get(key, float('nan')):.3f})",
        )
    ax.axhline(0.234, color="0.4", ls=":", lw=1.0, label="0.234 target (classic)")
    if rounds_p[-1] >= burnin_round:
        ax.axvspan(burnin_round, rounds_p[-1], color="0.85", alpha=0.35)
    ax.set_ylabel("Swap rate")
    ax.set_ylim(0.0, max(0.3, float(np.max(pt["a_swap_cum_round"])) * 1.4 + 0.02))
    ax.set_title(
        "PT — swap diagnostics by neighbor edge  |  "
        + ", ".join(f"{k}:{v:.3f}" for k, v in sorted(by_edge.items()))
    )
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=2)
    ax.grid(True, alpha=0.3)

    # --- 5. Local accept ---
    ax = axes[4]
    for w in range(n_rep):
        ax.plot(
            rounds_p,
            pt["a_local"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            alpha=0.55,
            lw=0.9,
            label=f"w{w} batch",
        )
        ax.plot(
            rounds_p,
            pt["a_cum"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            ls="--",
            lw=1.3,
            label=f"w{w} cum",
        )
    ax.axhline(0.5, color="0.5", ls=":", lw=1)
    ax.set_xlabel("Round")
    ax.set_ylabel("Local accept")
    ax.set_ylim(0.0, 1.05)
    ax.set_title("PT — local Metropolis accept (batch solid, cumulative dashed)")
    ax.legend(loc="best", fontsize=6, frameon=False, ncol=4)
    ax.grid(True, alpha=0.3)

    science = summary.get("science") or {}
    fig.supxlabel(
        f"problem={science.get('problem')}  bed={science.get('bed_shape')}  "
        f"rounds={len(rounds_p)}  replicas={n_rep}  "
        f"E_cold {pt['E_cold'][0]:.0f}→{pt['E_cold'][-1]:.0f}  "
        f"baseline_w0 {baseline['E'][0, 0]:.0f}→{baseline['E'][-1, 0]:.0f}",
        fontsize=9,
    )

    out = output_dir / f"{stem}_comparison.png"
    fig.savefig(out, dpi=150)
    fig.savefig(output_dir / f"{stem}_comparison.pdf")
    plt.close(fig)

    # Compact baseline-only overview
    fig2, axes2 = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    ax = axes2[0]
    for w in range(baseline["n_replicas"]):
        ax.plot(
            rounds_b,
            baseline["E"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.4,
            label=f"worker {w}",
        )
    ax.set_ylabel("Energy E")
    ax.set_title("Four-replica dual-cold baseline (exchange OFF, all T=1)")
    ax.legend(loc="best", fontsize=8, frameon=False)
    ax.grid(True, alpha=0.3)

    ax = axes2[1]
    for w in range(baseline["n_replicas"]):
        ax.plot(
            rounds_b,
            baseline["a_cum"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.4,
            label=f"worker {w} cum a_local",
        )
    ax.axhline(0.5, color="0.5", ls=":", lw=1)
    ax.set_xlabel("Round")
    ax.set_ylabel("Cumulative a_local")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="best", fontsize=8, frameon=False)
    ax.grid(True, alpha=0.3)

    out_b = output_dir / f"{stem}_baseline.png"
    fig2.savefig(out_b, dpi=150)
    fig2.savefig(output_dir / f"{stem}_baseline.pdf")
    plt.close(fig2)

    meta = {
        "baseline_run": str(baseline["run_dir"]),
        "pt_run": str(pt["run_dir"]),
        "figure_comparison_png": str(out),
        "figure_baseline_png": str(out_b),
        "temperatures_initial": temps0,
        "a_swap": a_swap,
        "swap_accepts": accepts,
        "swap_attempts": attempts,
        "a_swap_by_edge": by_edge,
        "rounds": len(rounds_p),
        "E_cold_start": float(pt["E_cold"][0]),
        "E_cold_end": float(pt["E_cold"][-1]),
        "baseline_E_end_per_worker": [float(x) for x in baseline["E"][-1]],
        "pt_E_end_per_worker": [float(x) for x in pt["E"][-1]],
        "caption": (
            "Matched four-replica Stancomb: dual-cold baseline (4×T=1, exchange off) "
            "vs PT ladder with neighbor odd/even swaps. Swap acceptance is low overall; "
            "compare PT cold-label energy to the four independent cold traces."
        ),
    }
    (output_dir / f"{stem}_summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=REPO_ROOT / "results" / "four_replica_stancomb_baseline_cold_r2000_T1.10match",
    )
    parser.add_argument(
        "--pt-dir",
        type=Path,
        default=REPO_ROOT / "results" / "four_replica_stancomb_pt_r2000_T1.10",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "figures" / "four_replica_stancomb_r2000_T1.10",
    )
    parser.add_argument("--stem", type=str, default="four_replica_stancomb_r2000_T1.10")
    parser.add_argument("--burnin-round", type=int, default=400)
    args = parser.parse_args()

    baseline = load_run(args.baseline_dir)
    pt = load_run(args.pt_dir)
    if baseline["summary"].get("exchange_enabled") is not False:
        raise SystemExit("baseline must have exchange_enabled=false")
    if pt["summary"].get("exchange_enabled") is not True:
        raise SystemExit("PT run must have exchange_enabled=true")
    if baseline["n_replicas"] != pt["n_replicas"]:
        raise SystemExit("baseline/PT replica counts differ")

    out = plot_comparison(
        baseline, pt, args.output_dir, args.stem, burnin_round=args.burnin_round
    )
    print(f"wrote {out}")
    print(f"wrote {args.output_dir / (args.stem + '_baseline.png')}")
    print(
        f"a_swap={pt['summary'].get('a_swap')}  "
        f"accepts={pt['summary'].get('swap_accepts')}/{pt['summary'].get('swap_attempts')}  "
        f"by_edge={pt['summary'].get('a_swap_by_edge')}  "
        f"E_cold {pt['E_cold'][0]:.1f} -> {pt['E_cold'][-1]:.1f}"
    )


if __name__ == "__main__":
    main()
