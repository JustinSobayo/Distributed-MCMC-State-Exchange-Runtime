#!/usr/bin/env python3
"""Matched dual-cold vs PT energy-trace figure (Panel A/B).

Panel A: PT cold-label energy (post-decision T=1) vs two dual-cold T=1 traces.
Panel B: per-worker PT energies, temperature markers, accepted-swap lines.
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


def _load_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def load_round_table(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_dir = run_dir.resolve()
    summary = _load_summary(run_dir / "summary.json")
    rows: list[dict[str, Any]] = []
    with (run_dir / "round_metrics.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            temps = _parse_list(raw["T"])
            energies = _parse_list(raw["E"])
            a_local = _parse_list(raw["a_local"])
            swap_accepted = str(raw.get("swap", "")).lower() in {"true", "1"}
            if raw.get("accepted") not in (None, ""):
                swap_accepted = str(raw["accepted"]).lower() in {"true", "1"}
            cold_idx = None
            if raw.get("cold_worker") not in (None, ""):
                cold_idx = int(float(raw["cold_worker"]))
            else:
                for i, t in enumerate(temps):
                    if abs(t - 1.0) < 1e-9:
                        cold_idx = i
                        break
            if cold_idx is None:
                raise ValueError(f"round {raw['round']}: no T=1 worker")
            rows.append(
                {
                    "round": int(raw["round"]),
                    "E": energies,
                    "T": temps,
                    "a_local": a_local,
                    "cold_idx": cold_idx,
                    "E_cold": energies[cold_idx],
                    "swap_accepted": swap_accepted,
                }
            )
    if not rows:
        raise ValueError(f"no rounds in {run_dir}")
    return summary, rows


def load_baseline(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, rows = load_round_table(run_dir)
    if summary.get("exchange_enabled") is not False:
        raise ValueError(f"{run_dir}: baseline must have exchange_enabled=false")
    if list(summary.get("temperatures_initial") or []) != [1.0, 1.0]:
        raise ValueError(f"{run_dir}: baseline temps must be [1,1]")
    return summary, rows


def load_pt(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, rows = load_round_table(run_dir)
    if summary.get("exchange_enabled") is not True:
        raise ValueError(f"{run_dir}: PT run must have exchange_enabled=true")
    return summary, rows


def assert_matched(baseline: dict[str, Any], pt: dict[str, Any]) -> None:
    b = baseline["resolved_config"]["sampling"]
    p = pt["resolved_config"]["sampling"]
    for key in ("batch_n_iterations", "rounds"):
        if b.get(key) != p.get(key):
            raise ValueError(f"mismatched sampling.{key}: baseline={b.get(key)} pt={p.get(key)}")


def plot_energy_trace(
    baseline_rows: list[dict[str, Any]],
    pt_rows: list[dict[str, Any]],
    baseline_summary: dict[str, Any],
    pt_summary: dict[str, Any],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rounds_b = [r["round"] for r in baseline_rows]
    rounds_p = [r["round"] for r in pt_rows]
    e0 = [r["E"][0] for r in baseline_rows]
    e1 = [r["E"][1] for r in baseline_rows]
    e_cold = [r["E_cold"] for r in pt_rows]
    e_w0 = [r["E"][0] for r in pt_rows]
    e_w1 = [r["E"][1] for r in pt_rows]
    t0 = [r["T"][0] for r in pt_rows]
    t1 = [r["T"][1] for r in pt_rows]
    swap_rounds = [r["round"] for r in pt_rows if r["swap_accepted"]]

    temps = pt_summary.get("temperatures_initial") or []
    a_swap = pt_summary.get("a_swap")
    accepts = pt_summary.get("swap_accepts")
    attempts = pt_summary.get("swap_attempts")

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, constrained_layout=True)

    ax = axes[0]
    ax.plot(rounds_b, e0, color="#1f77b4", alpha=0.75, lw=1.4, label="dual-cold worker 0")
    ax.plot(rounds_b, e1, color="#ff7f0e", alpha=0.75, lw=1.4, label="dual-cold worker 1")
    ax.plot(rounds_p, e_cold, color="#2ca02c", lw=2.0, label="PT cold label (T=1)")
    for s in swap_rounds:
        ax.axvline(s, color="0.35", ls="--", lw=1.0, alpha=0.7)
    if swap_rounds:
        ax.axvline(swap_rounds[0], color="0.35", ls="--", lw=1.0, alpha=0.7, label="accepted swap")
    ax.set_ylabel("Energy E")
    ax.set_title("Panel A — cold energy: dual-cold baseline vs PT cold label")
    ax.legend(loc="best", frameon=False, fontsize=9)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(rounds_p, e_w0, color="#1f77b4", lw=1.5, label="PT worker 0 energy")
    ax.plot(rounds_p, e_w1, color="#ff7f0e", lw=1.5, label="PT worker 1 energy")
    for s in swap_rounds:
        ax.axvline(s, color="0.35", ls="--", lw=1.0, alpha=0.7)
    ax.set_ylabel("Energy E")
    ax.set_xlabel("Round")
    ax.grid(True, alpha=0.3)

    ax_t = ax.twinx()
    ax_t.step(rounds_p, t0, where="post", color="#1f77b4", ls=":", lw=1.3, alpha=0.9, label="T worker 0")
    ax_t.step(rounds_p, t1, where="post", color="#ff7f0e", ls=":", lw=1.3, alpha=0.9, label="T worker 1")
    ax_t.set_ylabel("Temperature T")
    ax_t.set_ylim(0.8, max(temps + [1.5]) + 0.4)

    lines_a, labels_a = ax.get_legend_handles_labels()
    lines_b, labels_b = ax_t.get_legend_handles_labels()
    ax.legend(lines_a + lines_b, labels_a + labels_b, loc="best", fontsize=8, frameon=False)
    ax.set_title("Panel B — PT per-worker energy + temperatures (swap lines)")

    fig.suptitle(
        f"Stancomb matched pair  |  temps PT={temps}  |  "
        f"a_swap={a_swap} ({accepts}/{attempts})  |  "
        f"rounds={pt_summary.get('rounds')}",
        fontsize=11,
    )

    png = output_dir / "energy_trace_stancomb_r200.png"
    fig.savefig(png, dpi=160)
    fig.savefig(output_dir / "energy_trace_stancomb_r200.pdf")
    plt.close(fig)

    # Compact table for downstream use
    with (output_dir / "energy_trace_series.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "round",
                "baseline_E0",
                "baseline_E1",
                "pt_E_cold",
                "pt_E0",
                "pt_E1",
                "pt_T0",
                "pt_T1",
                "pt_swap_accepted",
            ],
        )
        writer.writeheader()
        for i, row in enumerate(pt_rows):
            writer.writerow(
                {
                    "round": row["round"],
                    "baseline_E0": e0[i] if i < len(e0) else "",
                    "baseline_E1": e1[i] if i < len(e1) else "",
                    "pt_E_cold": row["E_cold"],
                    "pt_E0": row["E"][0],
                    "pt_E1": row["E"][1],
                    "pt_T0": row["T"][0],
                    "pt_T1": row["T"][1],
                    "pt_swap_accepted": row["swap_accepted"],
                }
            )

    meta = {
        "baseline_run": str(baseline_summary.get("resolved_config", {}).get("runtime", {}).get("output_dir")),
        "pt_run": str(pt_summary.get("resolved_config", {}).get("runtime", {}).get("output_dir")),
        "temperatures_initial_pt": temps,
        "a_swap": a_swap,
        "swap_accepts": accepts,
        "swap_attempts": attempts,
        "swap_rounds": swap_rounds,
        "baseline_E0_end": e0[-1],
        "baseline_E1_end": e1[-1],
        "pt_E_cold_end": e_cold[-1],
        "figure_png": str(png),
        "interpretation": (
            "Low a_swap means few temperature exchanges; PT cold energy will track "
            "closely with dual-cold unless swaps move distinct beds onto T=1. "
            "Consider a milder ladder spacing or more intermediate temperatures."
        ),
    }
    (output_dir / "energy_trace_summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    return png


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-run-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "two_replica_stancomb_baseline_cold_r200",
    )
    parser.add_argument(
        "--pt-run-dir",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "two_replica_stancomb_pt_r200",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "figures" / "energy_trace_stancomb_r200",
    )
    args = parser.parse_args()

    b_summary, b_rows = load_baseline(args.baseline_run_dir)
    p_summary, p_rows = load_pt(args.pt_run_dir)
    assert_matched(b_summary, p_summary)
    out = plot_energy_trace(b_rows, p_rows, b_summary, p_summary, args.output_dir)
    print(f"wrote {out}")
    print(
        f"a_swap={p_summary.get('a_swap')}  "
        f"accepts={p_summary.get('swap_accepts')}/{p_summary.get('swap_attempts')}"
    )


if __name__ == "__main__":
    main()
