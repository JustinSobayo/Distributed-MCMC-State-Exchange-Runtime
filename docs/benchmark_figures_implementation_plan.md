# Implementation plan: trustworthy synthetic PT benchmark figures

**Status:** draft for Justin’s review (do not treat as done until checked off)  
**Scope:** matched dual-cold vs PT energy-trace (Stancomb preferred once two-replica supports it; synthetic still valid for plumbing)  
**Related:** `stancomb_single_chain_visualization_plan.md` (do single-chain Stancomb plots first from local archive), `python_pt_coordinator.md`, `benchmark_metrics.md`  
**Plot outputs:** repo-root `figures/` (not `MCMC_implementation/figures/`)

---

## 1. Plain-language answers

### What is a “matched dual-cold baseline artifact”?

It is a **saved run directory** (metrics + config fingerprint) from:

> **two independent \(T=1\) chains, exchange OFF**

Same synthetic problem, same batch size / proposal budget rules, and comparable seeds as the PT run you will plot against.

It is **not**:
- two PT chains that both somehow stay cold
- one single-chain baseline alone (useful sanity check, but not the equal-resource comparison)
- a PT run with `exchange.enabled: true`

In this repo that is exactly the profile:

`MCMC_implementation/configs/two_replica_baseline_cold.yaml`  
→ temperatures `[1.0, 1.0]`, `exchange.enabled: false`

“Matched” means: when you compare PT vs baseline in Panel A, both runs used the **same target, same budget definition, and documented seed policy**. The artifact is the on-disk proof of that baseline run (`round_metrics`, `summary`, resolved config).

### Two individual cold chains, or two PT cold chains?

**Two individual / independent cold chains** (both \(T=1\), no temperature swaps).

PT always has one cold label (\(T=1\)) and usually one hot (\(T>1\)). After swaps, *which worker* holds cold can change — but that is still **one** cold sampling process for inference, not “two PT cold chains.”

| Setup | Temperatures | Exchange | Role |
| --- | --- | --- | --- |
| Dual-cold baseline (B1) | `[1, 1]` | off | Equal-resource “without PT” |
| PT | `[1, T_hot]` | on | Method under test |
| Single cold (B0) | one chain `@1` | n/a | Debug / sanity only |

### What is the time-breakdown figure?

A **systems / overhead** plot, not a science-quality plot.

It answers: *of each synchronized round, how much time was spent in*

- local MCMC compute  
- sending/reporting status  
- waiting at the barrier (fast worker idle until slow worker + coordinator finish)  
- coordinator decision / assignment broadcast  

So yes: it measures **how long each part of your distributed system takes**, to judge whether sync/network overhead is worth it.

It does **not** by itself prove PT improves bed exploration. That is the energy-trace / cold-chain comparison figure.

You **cannot** make a trustworthy time-breakdown figure yet, because timings are still lumped into coordinator-side `t_compute_ms`. That needs worker-side + barrier-split instrumentation first.

The **energy-trace figure does not need that instrumentation**.

---

## 2. Goal (what “done” means)

Produce reproducible synthetic evidence that you can show and explain:

1. **Science/systems sampling figure (energy trace)**  
   - Panel A: PT’s current \(T=1\) energy vs two independent \(T=1\) baseline traces  
   - Panel B: each worker’s local energy + temperature markers + accepted-exchange lines  

2. **Systems overhead figure (time breakdown)** — after timing instrumentation  
   - stacked per-round compute / wait / communicate / coordinator  

3. **Clear docs** stating what each figure can and cannot claim (synthetic ≠ glacier truth).

---

## 3. What you already have

- Tempered local accept in bundled Niya (`/T`, default 1)  
- Python coordinator + two outbound workers + swap Metropolis  
- PT and dual-cold YAML profiles  
- Round metrics with `E`, `T_before`, `T`, swap decision, local accepts, coarse times  
- Single-chain baseline harness + Stancomb builder (optional later; not required for this synthetic figure slice)

---

## 4. Phased plan

### Phase A — Matched dual-cold baseline artifact (small, do first)

**Goal:** Have a baseline run folder you can point the energy-trace plotter at.

1. Run dual-cold baseline with the same synthetic settings / budget as the PT smoke (or a longer shared profile).  
2. Write outputs under a dedicated run id, e.g. `results/synthetic_baseline_dual_cold_<stamp>/` (avoid overwriting).  
3. Confirm `exchange_enabled: false`, both temps `1.0`, and round count / batch size match the PT comparison run.  
4. Optionally re-run PT into a sibling `results/synthetic_pt_<stamp>/` so both artifacts are fresh and paired.

**Exit:** two run directories exist; configs recorded; you can name them in a plot command.

### Phase B — Energy-trace figure (primary near-term deliverable)

**Goal:** Implement the energy-trace handoff without waiting on barrier timers.

1. Adapter: read existing `round_metrics.json` (+ summary) **or** add thin JSONL export at end of coordinator run (`worker_round_complete` / `exchange_attempt` derived from current records). Prefer minimal change: transform existing JSON → plot tables.  
2. CLI `scripts/plot_energy_trace.py` (or under `MCMC_implementation/scripts/`) that takes `--pt-run-dir` and `--baseline-run-dirs`.  
3. Build Panel A cold series from post-decision \(T=1\) worker energy.  
4. Build Panel B from stable worker energies + markers + accepted-exchange verticals.  
5. Emit PNG/PDF/CSV/`energy_trace_summary.json` + short `docs/energy_trace_figure.md`.  
6. Fixture tests: accept/reject swap assignment logic; cold selection; baseline must be \(T=1\) only.

**Exit:** one command produces the two-panel figure from baseline + PT artifacts.

**Does not require:** worker barrier timing.

### Phase C — Worker-side + barrier-split instrumentation (enables time figure)

**Goal:** Make round timing scientifically attributable.

1. Worker STATUS adds: `compute_seconds`, `report_send_seconds` (and later `barrier_wait_seconds`).  
2. Define barrier wait consistently: after report sent → until next assignment/command received.  
3. Coordinator logs `coordinator_decision_seconds`, `assignment_broadcast_seconds`, and writes `exchange_metrics.jsonl` / `round_metrics.jsonl` with `run_id` + immutable `config.json`.  
4. No double-counting: document which clocks are nested vs exclusive.  
5. Keep protocol backward-compatible where practical (extra STATUS fields).

**Exit:** a PT run’s JSONL can rebuild compute vs wait vs send without using lumped `t_compute_ms`.

### Phase D — Time-breakdown figure

**Goal:** Stacked bars (+ summary means) from Phase C telemetry.

1. `scripts/plot_pt_benchmark.py` (or dedicated time plotter) → `time_breakdown.png` + CSV.  
2. Compare baseline dual-cold vs PT cadence pilots (`batch` 10 / 50 / 200) under same proposal budget.  
3. Docs: how to read wide compute vs wide wait vs communication.

**Exit:** overhead figure generated from instrumented runs only (refuse to plot if split timings missing).

### Phase E — Harder synthetic / Stancomb (figure usefulness)

Current synthetic bowl yields ~100% local accept and near-always swaps — traces look flat.

1. Either toughen synthetic (stronger constraints / noisier target) **or** move comparison to Stancomb once wired into PT configs.  
2. Re-run matched baseline + PT; regenerate figures.  
3. Judge PT by cold-chain exploration diagnostics (see `benchmark_metrics.md`), not “hot acceptance went up.”

---

## 5. Suggested order of work (review checklist)

- [ ] **A1** Produce matched dual-cold baseline run artifact  
- [ ] **A2** Produce paired PT run artifact (same budget)  
- [ ] **B1** Plot pipeline for energy-trace comparison  
- [ ] **B2** Docs + fixture tests for energy figure  
- [ ] **C1** Worker/coordinator split timing + JSONL  
- [ ] **D1** Time-breakdown plots  
- [ ] **E1** Harder target so figures show real structure  

Recommended stop point for the next coding session: **finish A + B** (energy figure). Defer C/D until you care about overhead slides.

---

## 6. Explicit non-goals for this plan

- C++ coordinator  
- Flame graphs / Nsight  
- Claiming glacier reconstruction accuracy from synthetic plots  
- Async exchange or >2 replicas (schemas may stay forward-compatible)

---

## 7. Decision points for Justin

1. **X-axis:** completed **round** (recommended) vs MCMC iteration?  
2. **Baseline seeds:** two workers with `seed` / `seed+1` (current launcher) OK for “independent,” or require two fully separate single-chain jobs?  
3. **Telemetry format:** adapt existing `round_metrics.json` first, or invest now in JSONL schemas from the full benchmark handoff?  
4. **Next coding slice:** approve **A+B only**, or jump straight into **C** timing instrumentation as well?

---

## 8. One-sentence summary

**Dual-cold baseline = two independent \(T=1\) chains with swaps off (saved run folder); energy-trace figure compares that to PT’s moving cold label; time-breakdown figure measures system component runtimes and is blocked until worker/barrier timers exist — implement baseline artifact + energy plots first.**
