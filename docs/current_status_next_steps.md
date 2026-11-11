# Current status, goals, and next steps

**Date:** 2026-11-11  
**Audience:** Justin (working notes for the next coding / HPG session)  
**Related:** `stancomb_two_replica_pt_enablement_plan.md`, `benchmark_figures_implementation_plan.md`, `stancomb_single_chain_visualization_plan.md`

---

## 1. Where you are right now

### Done (runtime / science wiring)

| Piece | Status |
| --- | --- |
| Tempered local Metropolis in Niya (`exp((E_prev−E_next)/T)`) | Done |
| Python two-replica PT coordinator + outbound workers | Done |
| Swap Metropolis on coordinator | Done |
| Stancomb science on the two-replica path (`problem_factory`, CLI flags, fingerprint) | Done |
| Configurable `register_timeout_seconds` (Stancomb CRF build >120s) | Done |
| Dual-cold + PT Stancomb YAML profiles | Done |
| HPG interactive `srun` workflow (gly4930, localhost TCP on one node) | Proven |

### Done (runs / evidence)

| Run | Where | What it proved |
| --- | --- | --- |
| Single-chain Stancomb cold smoke | Archived locally under `benchmarks/20261110_094921_BASELINE_stancomb_single_cold/` | Stancomb builder + metrics path |
| Dual-cold + PT **2-round smoke** | HPG `results/two_replica_stancomb_{baseline_cold,pt}/` | End-to-end wiring; REGISTER after long CRF setup |
| Dual-cold + PT **r40** (50 props/round × 40 rounds) | HPG `results/two_replica_stancomb_{baseline_cold,pt}_r40/` | Matched pair; energies ~186k→167k; PT `a_swap≈0.1` (~4/40 accepts) |

**Important:** r40 finished successfully even after Wi‑Fi drop — artifacts live on `/blue`, not yet copied into local `benchmarks/`.

### In progress / prepared but not finished

- Local YAMLs already set for a longer matched pair: **`batch_n_iterations: 101`, `rounds: 200`** → `…_r200` output dirs (edit may still need to be mirrored on HPG via nano / pull).
- GPU Stancomb / CUDA path exists in the broader Niya tree but is **not** plugged into the two-replica launcher yet (`backend: cpu` in current YAMLs).
- Energy-trace figure pipeline from `benchmark_figures_implementation_plan.md` **not implemented** yet.
- Time-breakdown figure **blocked** on worker/barrier split timers (do not start yet).

### Explicitly deferred

- C++ coordinator  
- Multi-node TCP (still one-node `127.0.0.1`)  
- Temperature ladder >2 replicas  
- Claiming scientific PT gains from short traces  
- Overnight paper-length budgets on CPU until archive + plot loop works

---

## 2. Goals (what “success” looks like next)

### Near-term (this week)

1. **Keep a durable matched Stancomb pair** under `benchmarks/` (r40 minimum; r200 preferred).  
2. **Plot energy-trace Panel A/B** comparing dual-cold vs PT cold label — first trustworthy Stancomb PT figure.  
3. **Decide temperature / ladder policy** from r40/r200 swap stats (`a_swap≈0.1` is low; milder \(T_\text{hot}\) or intermediate rungs may be needed).  
4. **Operational habit:** long HPG runs inside `tmux` so laptop disconnects are safe.

### Medium-term (after figures exist)

5. Move longer PT / infrastructure iteration to **GPU** so wall time is not dominated by waiting to experiment.  
6. Add worker-side timing → **time-breakdown** overhead figure.  
7. Optional: multi-node exchange, more replicas, C++ coordinator — only after Python PT evidence is solid.

---

## 3. What is next (ordered)

### Next 1 — Sync longer configs on HPG and run r200 (optional but recommended)

On compute node, both YAMLs should match:

- `batch_n_iterations: 101`  
- `rounds: 200`  
- `log_every_rounds: 10`  
- `output_dir: …_r200`  

```bash
# inside tmux on the allocated node
$PY MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/two_replica_stancomb_baseline_cold.yaml

$PY MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/two_replica_stancomb_pt.yaml
```

**Exit:** `results/two_replica_stancomb_{baseline_cold,pt}_r200/` both `PT DONE`.

If short on time, **skip to Next 2 with r40** — that pair is already enough to stand up the plotter.

### Next 2 — Archive HPG results into local `benchmarks/`

From laptop (or HPG → local rsync):

```text
benchmarks/<stamp>_BASELINE_stancomb_dual_cold_r40/   # or r200
benchmarks/<stamp>_PT_stancomb_two_replica_r40/       # or r200
```

Each folder: README (node, budget, `a_swap`, seeds), `round_metrics.*`, `summary.json`, fingerprint / resolved config.

**Exit:** plot inputs exist in-repo without needing HPG live.

### Next 3 — Energy-trace figure (primary coding milestone)

Follow `benchmark_figures_implementation_plan.md` Phase B:

1. Read existing `round_metrics` (no new timers required).  
2. CLI: `--pt-run-dir` + `--baseline-run-dirs`.  
3. Panel A: PT cold (\(T=1\)) energy vs two dual-cold traces.  
4. Panel B: per-worker energy + T markers + accepted-swap lines.  
5. Write under repo-root `figures/`.

**Exit:** one command produces the two-panel figure from archived r40 or r200.

### Next 4 — Interpret and tune (science / PT knobs)

From the figure + `a_swap`:

- If swaps stay rare: try \(T_\text{hot}\in\{1.3,1.5,1.7\}\) or plan a 3+ temperature ladder.  
- If cold energies look similar dual-cold vs PT: need longer budgets and/or better ladder before claiming PT help.  
- Keep local accept on cold near the single-chain baseline (~0.5).

### Next 5 — GPU enablement for the two-replica path

Only after Next 2–3 so you are not blocked on plotting:

1. Confirm GPU Niya / adapter path builds Stancomb identically.  
2. Wire `science.backend: gpu` (or equivalent) through factory + worker.  
3. HPG GPU partition smoke (short), then long PT experiments for infrastructure work.

### Next 6 — Systems timing (later)

Phase C/D of the benchmark figures plan: worker compute / report / barrier wait split → time-breakdown stacked bars. Do **not** block energy-trace on this.

---

## 4. Checklist

- [x] Stancomb two-replica wiring  
- [x] HPG dual-cold + PT smoke  
- [x] HPG matched r40 pair (`a_swap≈0.1`)  
- [ ] HPG r200 pair (optional)  
- [ ] Archive dual-cold + PT under `benchmarks/`  
- [ ] Energy-trace plotter + first Stancomb PT figure  
- [ ] Temperature / ladder tweak based on swap rate  
- [ ] GPU two-replica path for long experiments  
- [ ] Worker/barrier timing + time-breakdown figure  

---

## 5. Operational reminders

- Login node ≠ compute: `srun … --pty bash`, then `hostname`, then `ssh <node>` from a second terminal.  
- Long runs: `tmux new -s pt` before launching; detach with `Ctrl+b d`.  
- Closing the laptop without tmux/batch kills interactive `srun` jobs.  
- Matched compare rule: same science, same `batch_n_iterations` / `rounds`, only temps + `exchange.enabled` differ.

---

## 6. One-line summary

**Stancomb dual-cold and PT now run end-to-end on HPG (r40 in hand); next is archive → energy-trace figure → tune temps/ladder; GPU and timing instrumentation come after that so you can iterate on infrastructure without waiting on missing plots.**
