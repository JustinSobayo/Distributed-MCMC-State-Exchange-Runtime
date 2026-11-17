#!/usr/bin/env python3
"""Visualize matched four-replica Stancomb dual-cold vs PT runs.

Reads round_metrics.json (preferred) or round_metrics.csv + summary.json.
Writes:
  - comparison PNG (baseline vs PT cold, PT energies, T, swaps, a_local)
  - baseline-only PNG
  - PT-only standardized trace PNG (energy / a_local / swaps+T / time)
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

WORKER_COLORS = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b")
COLD_COLOR = "#111111"
SWAP_COLOR = "0.35"
COORD_COLOR = "#2ca02c"


def _rolling_mean(values: list[float], window: int) -> np.ndarray:
    if window <= 1:
        return np.asarray(values, dtype=float)
    out = np.empty(len(values), dtype=float)
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        out[i] = float(np.mean(values[lo : i + 1]))
    return out


def _parse_cell(cell: str) -> Any:
    if cell is None or cell == "":
        return None
    try:
        return json.loads(cell)
    except json.JSONDecodeError:
        return ast.literal_eval(cell)


def _rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row: dict[str, Any] = {"round": int(raw["round"])}
            for key in (
                "replica_ids",
                "E",
                "T_before",
                "T",
                "a_local",
                "a_local_cumulative",
                "accepted_this_batch",
                "attempted_this_batch",
                "t_compute_ms",
                "swaps",
            ):
                if key in raw and raw[key] not in (None, ""):
                    row[key] = _parse_cell(raw[key])
            row["t_coord_ms"] = float(raw["t_coord_ms"])
            row["exchange_enabled"] = str(raw.get("exchange_enabled", "")).lower() in {
                "true",
                "1",
            }
            row["swap"] = str(raw.get("swap", "")).lower() in {"true", "1"}
            row["accepted"] = str(raw.get("accepted", "")).lower() in {"true", "1"}
            if raw.get("cold_worker") not in (None, ""):
                row["cold_worker"] = int(float(raw["cold_worker"]))
            else:
                row["cold_worker"] = None
            if raw.get("p_swap") not in (None, ""):
                row["p_swap"] = float(raw["p_swap"])
            rows.append(row)
    return rows


def load_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    summary = json.loads((run_dir / "summary.json").read_text())
    json_path = run_dir / "round_metrics.json"
    csv_path = run_dir / "round_metrics.csv"
    if json_path.is_file():
        rows = json.loads(json_path.read_text())
    elif csv_path.is_file():
        rows = _rows_from_csv(csv_path)
    else:
        raise FileNotFoundError(f"missing round_metrics.json/.csv under {run_dir}")
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

    cold_idx: list[int] = []
    e_cold: list[float] = []
    for r, energies, temps in zip(rows, E, T):
        ci = r.get("cold_worker")
        if ci is None:
            matches = [i for i, t in enumerate(temps) if abs(float(t) - 1.0) < 1e-9]
            ci = int(matches[0]) if matches else 0
        else:
            ci = int(ci)
        # cold_worker is replica_id; rows store E in ordered replica_id order
        cold_idx.append(ci)
        e_cold.append(float(energies[ci]))

    accepted_round = [bool(r.get("accepted") or r.get("swap")) for r in rows]
    swap_rounds = [rd for rd, ok in zip(rounds, accepted_round) if ok]

    edge_keys: list[str] = []
    edge_accept_series: dict[str, list[float]] = {}
    edge_attempt_series: dict[str, list[float]] = {}
    for r in rows:
        for s in r.get("swaps") or []:
            key = f"{int(s['i'])}-{int(s['j'])}"
            if key not in edge_accept_series:
                edge_keys.append(key)
                edge_accept_series[key] = [0.0] * len(rows)
                edge_attempt_series[key] = [0.0] * len(rows)
    for i, r in enumerate(rows):
        for s in r.get("swaps") or []:
            key = f"{int(s['i'])}-{int(s['j'])}"
            edge_attempt_series[key][i] = 1.0
            if s.get("accepted"):
                edge_accept_series[key][i] = 1.0

    a_swap_cum: list[float] = []
    n_acc = 0
    for ok in accepted_round:
        if ok:
            n_acc += 1
        a_swap_cum.append(n_acc / float(len(a_swap_cum) + 1))

    # Exact attempt/accept cumulative from edge events (better than round-or)
    attempt_events = 0
    accept_events = 0
    a_swap_event_cum: list[float] = []
    for r in rows:
        swaps = r.get("swaps") or []
        for s in swaps:
            attempt_events += 1
            if s.get("accepted"):
                accept_events += 1
        a_swap_event_cum.append(
            (accept_events / float(attempt_events)) if attempt_events else 0.0
        )

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
        "edge_attempt_series": edge_attempt_series,
        "a_swap_cum_round": a_swap_cum,
        "a_swap_cum_events": a_swap_event_cum,
    }


def post_burnin_edge_rates(
    run: dict[str, Any], burnin_round: int
) -> dict[str, float]:
    rounds = run["rounds"]
    out: dict[str, float] = {}
    for key in run["edge_keys"]:
        attempts = 0
        accepts = 0
        for i, rd in enumerate(rounds):
            if rd < burnin_round:
                continue
            attempts += int(run["edge_attempt_series"][key][i])
            accepts += int(run["edge_accept_series"][key][i])
        out[key] = (accepts / float(attempts)) if attempts else float("nan")
    return out


def _mark_swaps(ax: Any, swap_rounds: list[int]) -> None:
    if not swap_rounds:
        return
    if len(swap_rounds) > 60:
        ax.axvline(swap_rounds[0], color=SWAP_COLOR, ls="--", lw=1.2, alpha=0.85)
        return
    for s in swap_rounds:
        ax.axvline(s, color=SWAP_COLOR, ls="--", lw=0.8, alpha=0.45)


def plot_baseline(baseline: dict[str, Any], output_dir: Path, stem: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rounds_b = baseline["rounds"]
    n_rep = baseline["n_replicas"]

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, constrained_layout=True)

    ax = axes[0]
    for w in range(n_rep):
        ax.plot(
            rounds_b,
            baseline["E"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.4,
            label=f"worker {w}",
        )
    ax.set_ylabel("Energy E")
    ax.set_title("Four-replica dual-cold baseline — exchange OFF, all T=1")
    ax.legend(loc="best", fontsize=8, frameon=False, ncol=2)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for w in range(n_rep):
        ax.plot(
            rounds_b,
            baseline["a_local"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            alpha=0.55,
            lw=0.9,
            label=f"w{w} batch",
        )
        ax.plot(
            rounds_b,
            baseline["a_cum"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            ls="--",
            lw=1.3,
            label=f"w{w} cum",
        )
    ax.axhline(0.5, color="0.5", ls=":", lw=1)
    ax.set_ylabel("Local accept")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=4)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    for w in range(n_rep):
        ax.plot(
            rounds_b,
            baseline["t_compute"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.0,
            label=f"w{w} compute",
        )
    ax.plot(rounds_b, baseline["t_coord"], color=COORD_COLOR, lw=1.2, label="coordinator")
    ax.set_xlabel("Round")
    ax.set_ylabel("Time (ms)")
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=3)
    ax.grid(True, alpha=0.3)

    out = output_dir / f"{stem}_baseline.png"
    fig.savefig(out, dpi=150)
    fig.savefig(output_dir / f"{stem}_baseline.pdf")
    plt.close(fig)
    return out


def plot_pt_trace(
    pt: dict[str, Any],
    output_dir: Path,
    stem: str,
    *,
    burnin_round: int = 400,
) -> Path:
    """PT-only standardized figure for poster / diagnostics."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rounds = pt["rounds"]
    n_rep = pt["n_replicas"]
    summary = pt["summary"]
    temps0 = summary.get("temperatures_initial") or []
    a_swap = summary.get("a_swap")
    accepts = summary.get("swap_accepts")
    attempts = summary.get("swap_attempts")
    by_edge = summary.get("a_swap_by_edge") or {}
    post_edge = post_burnin_edge_rates(pt, burnin_round)

    fig, axes = plt.subplots(4, 1, figsize=(11, 12), sharex=True, constrained_layout=True)

    ax = axes[0]
    for w in range(n_rep):
        ax.plot(
            rounds,
            pt["E"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.2,
            label=f"worker {w}",
        )
    ax.plot(rounds, pt["E_cold"], color=COLD_COLOR, lw=2.0, label="cold label (T=1)")
    if rounds[-1] >= burnin_round:
        ax.axvspan(burnin_round, rounds[-1], color="0.85", alpha=0.35, label="post-burn-in")
    _mark_swaps(ax, pt["swap_rounds"])
    ax.set_ylabel("Energy E")
    ax.set_title(
        f"PT Stancomb 4-replica — temps {temps0}  |  "
        f"a_swap={a_swap:.4f} ({accepts}/{attempts})"
    )
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=3)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for w in range(n_rep):
        ax.plot(
            rounds,
            pt["a_local"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            alpha=0.55,
            lw=0.9,
            label=f"w{w} batch",
        )
        ax.plot(
            rounds,
            pt["a_cum"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            ls="--",
            lw=1.2,
            label=f"w{w} cum",
        )
    ax.axhline(0.5, color="0.5", ls=":", lw=1)
    ax.set_ylabel("Local accept")
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="best", fontsize=6, frameon=False, ncol=4)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(
        rounds,
        pt["a_swap_cum_events"],
        color="#8c564b",
        lw=1.8,
        label="cumulative a_swap (pair attempts)",
    )
    for key in pt["edge_keys"]:
        ax.plot(
            rounds,
            _rolling_mean(pt["edge_accept_series"][key], 50),
            lw=1.2,
            label=(
                f"edge {key} win50 "
                f"(all={by_edge.get(key, float('nan')):.3f}, "
                f"post≥{burnin_round}={post_edge.get(key, float('nan')):.3f})"
            ),
        )
    ax.axhline(0.234, color="0.4", ls=":", lw=1.0, label="0.234 target")
    if rounds[-1] >= burnin_round:
        ax.axvspan(burnin_round, rounds[-1], color="0.85", alpha=0.35)
    ax.set_ylabel("Swap rate")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)

    ax_t = ax.twinx()
    for w in range(n_rep):
        ax_t.step(
            rounds,
            pt["T"][:, w],
            where="post",
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            ls=":",
            lw=1.1,
            alpha=0.85,
            label=f"T{w}",
        )
    ax_t.set_ylabel("Temperature T")
    t_hi = max(list(temps0) + [1.1]) + 0.05
    ax_t.set_ylim(0.95, t_hi)
    lines_l, labels_l = ax.get_legend_handles_labels()
    lines_r, labels_r = ax_t.get_legend_handles_labels()
    ax.legend(lines_l + lines_r, labels_l + labels_r, loc="best", fontsize=6, frameon=False, ncol=2)
    ax.set_title("Parallel tempering — per-edge swaps + temperatures")

    ax = axes[3]
    for w in range(n_rep):
        ax.plot(
            rounds,
            pt["t_compute"][:, w],
            color=WORKER_COLORS[w % len(WORKER_COLORS)],
            lw=1.0,
            label=f"w{w} compute",
        )
    ax.plot(rounds, pt["t_coord"], color=COORD_COLOR, lw=1.2, label="coordinator")
    _mark_swaps(ax, pt["swap_rounds"])
    ax.set_xlabel("Round")
    ax.set_ylabel("Time (ms)")
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=3)
    ax.grid(True, alpha=0.3)

    science = summary.get("science") or {}
    fig.supxlabel(
        f"problem={science.get('problem')}  bed={science.get('bed_shape')}  "
        f"rounds={len(rounds)}  replicas={n_rep}  temps={temps0}  "
        f"a_swap={a_swap}  by_edge={ {k: round(v, 4) for k, v in sorted(by_edge.items())} }",
        fontsize=8,
    )

    out = output_dir / f"{stem}_pt_trace.png"
    fig.savefig(out, dpi=150)
    fig.savefig(output_dir / f"{stem}_pt_trace.pdf")
    plt.close(fig)
    return out


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
    post_edge = post_burnin_edge_rates(pt, burnin_round)

    fig, axes = plt.subplots(5, 1, figsize=(11, 14), sharex=False, constrained_layout=True)

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
    ax.set_title("PT — per-worker energy")
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=3)
    ax.grid(True, alpha=0.3)

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
    ax.set_title("PT — temperature assignment per worker")
    ax.legend(loc="best", fontsize=7, frameon=False, ncol=4)
    ax.grid(True, alpha=0.3)

    ax = axes[3]
    ax.plot(
        rounds_p,
        pt["a_swap_cum_events"],
        color="#8c564b",
        lw=1.6,
        label="cumulative a_swap (pair attempts)",
    )
    for key in pt["edge_keys"]:
        series = pt["edge_accept_series"][key]
        ax.plot(
            rounds_p,
            _rolling_mean(series, 50),
            lw=1.3,
            label=(
                f"edge {key} win50 "
                f"(all={by_edge.get(key, float('nan')):.3f}, "
                f"post={post_edge.get(key, float('nan')):.3f})"
            ),
        )
    ax.axhline(0.234, color="0.4", ls=":", lw=1.0, label="0.234 target")
    if rounds_p[-1] >= burnin_round:
        ax.axvspan(burnin_round, rounds_p[-1], color="0.85", alpha=0.35)
    ax.set_ylabel("Swap rate")
    ymax = max(0.35, float(np.nanmax(pt["a_swap_cum_events"])) * 1.5 + 0.05)
    ax.set_ylim(0.0, min(1.05, ymax))
    ax.set_title(
        "PT — swap diagnostics by neighbor edge  |  "
        + ", ".join(f"{k}:{v:.3f}" for k, v in sorted(by_edge.items()))
    )
    ax.legend(loc="best", fontsize=6, frameon=False, ncol=2)
    ax.grid(True, alpha=0.3)

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
    return out


def write_meta(
    baseline: dict[str, Any],
    pt: dict[str, Any],
    output_dir: Path,
    stem: str,
    paths: dict[str, str],
    *,
    burnin_round: int,
) -> Path:
    summary = pt["summary"]
    meta = {
        "baseline_run": str(baseline["run_dir"]),
        "pt_run": str(pt["run_dir"]),
        "figures": paths,
        "temperatures_initial": summary.get("temperatures_initial"),
        "a_swap": summary.get("a_swap"),
        "swap_accepts": summary.get("swap_accepts"),
        "swap_attempts": summary.get("swap_attempts"),
        "a_swap_by_edge": summary.get("a_swap_by_edge"),
        "a_swap_by_edge_post_burnin": post_burnin_edge_rates(pt, burnin_round),
        "burnin_round": burnin_round,
        "rounds": len(pt["rounds"]),
        "E_cold_start": float(pt["E_cold"][0]),
        "E_cold_end": float(pt["E_cold"][-1]),
        "baseline_E_end_per_worker": [float(x) for x in baseline["E"][-1]],
        "pt_E_end_per_worker": [float(x) for x in pt["E"][-1]],
        "caption": (
            "Matched four-replica Stancomb: dual-cold baseline (4×T=1, exchange off) "
            "vs PT ladder with neighbor odd/even swaps. Report per-edge a_swap and "
            "compare PT cold-label energy to the four independent cold traces."
        ),
    }
    out = output_dir / f"{stem}_summary.json"
    out.write_text(json.dumps(meta, indent=2) + "\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=REPO_ROOT
        / "benchmarks"
        / "four_replica_stancomb_baseline_cold_r2000_T1.05match",
    )
    parser.add_argument(
        "--pt-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "four_replica_stancomb_pt_r2000_T1.05",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "figures" / "four_replica_stancomb_r2000_T1.05",
    )
    parser.add_argument("--stem", type=str, default="four_replica_stancomb_r2000_T1.05")
    parser.add_argument("--burnin-round", type=int, default=400)
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Only plot the dual-cold baseline (skip PT / comparison).",
    )
    parser.add_argument(
        "--pt-only",
        action="store_true",
        help="Only plot the PT run (skip baseline / comparison).",
    )
    args = parser.parse_args()

    if args.baseline_only and args.pt_only:
        raise SystemExit("choose at most one of --baseline-only / --pt-only")

    if args.pt_only:
        pt = load_run(args.pt_dir)
        if pt["summary"].get("exchange_enabled") is not True:
            raise SystemExit("PT run must have exchange_enabled=true")
        out_pt = plot_pt_trace(
            pt, args.output_dir, args.stem, burnin_round=args.burnin_round
        )
        print(f"wrote {out_pt}")
        print(
            f"a_swap={pt['summary'].get('a_swap')}  "
            f"accepts={pt['summary'].get('swap_accepts')}/{pt['summary'].get('swap_attempts')}  "
            f"by_edge={pt['summary'].get('a_swap_by_edge')}  "
            f"E_cold {pt['E_cold'][0]:.1f} -> {pt['E_cold'][-1]:.1f}"
        )
        return

    baseline = load_run(args.baseline_dir)
    if baseline["summary"].get("exchange_enabled") is not False:
        raise SystemExit("baseline must have exchange_enabled=false")

    if args.baseline_only:
        out_base = plot_baseline(baseline, args.output_dir, args.stem)
        print(f"wrote {out_base}")
        print(
            f"baseline E0 {baseline['E'][0, 0]:.1f} -> {baseline['E'][-1, 0]:.1f}  "
            f"rounds={len(baseline['rounds'])}  replicas={baseline['n_replicas']}"
        )
        return

    pt = load_run(args.pt_dir)
    if pt["summary"].get("exchange_enabled") is not True:
        raise SystemExit("PT run must have exchange_enabled=true")
    if baseline["n_replicas"] != pt["n_replicas"]:
        raise SystemExit("baseline/PT replica counts differ")

    out_cmp = plot_comparison(
        baseline, pt, args.output_dir, args.stem, burnin_round=args.burnin_round
    )
    out_base = plot_baseline(baseline, args.output_dir, args.stem)
    out_pt = plot_pt_trace(pt, args.output_dir, args.stem, burnin_round=args.burnin_round)
    write_meta(
        baseline,
        pt,
        args.output_dir,
        args.stem,
        {
            "comparison_png": str(out_cmp),
            "baseline_png": str(out_base),
            "pt_trace_png": str(out_pt),
        },
        burnin_round=args.burnin_round,
    )
    print(f"wrote {out_cmp}")
    print(f"wrote {out_base}")
    print(f"wrote {out_pt}")
    print(
        f"a_swap={pt['summary'].get('a_swap')}  "
        f"accepts={pt['summary'].get('swap_accepts')}/{pt['summary'].get('swap_attempts')}  "
        f"by_edge={pt['summary'].get('a_swap_by_edge')}  "
        f"E_cold {pt['E_cold'][0]:.1f} -> {pt['E_cold'][-1]:.1f}"
    )


if __name__ == "__main__":
    main()
