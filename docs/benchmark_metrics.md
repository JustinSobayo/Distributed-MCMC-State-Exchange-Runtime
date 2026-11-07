# Benchmark metrics glossary

Canonical definitions for every quantity we track when comparing baselines
(Bakari-style single-chain, synthetic cold, equal-resource dual-cold) to
parallel tempering (PT). Dated run folders under `benchmarks/` should only
**store results**; this file is the meaning of the columns.

Related: [`single_chain_baseline.md`](single_chain_baseline.md),
[`python_pt_coordinator.md`](python_pt_coordinator.md),
[`benchmarks/README.md`](../benchmarks/README.md).

---

## What we are measuring (and what we are not)

**Primary scientific question:** Does temperature-exchange PT improve
**cold-chain** (\(T=1\)) exploration relative to an equal-resource run
without PT?

**Not the primary score:** Hot-replica local acceptance going up (expected
when \(T>1\)), or raw wall-clock alone without a fixed proposal budget.

**Systems question (separate):** Does the coordinator/worker TCP path
complete rounds with acceptable overhead on HiPerGator?

---

## Core metrics

### Wall time (`wall_s`, `batch_wall_s`, `t_coord_ms`, `t_compute_ms`)

**Wall time** is elapsed **clock** time from start to finish (or per batch /
round): how long you waited, not “CPU seconds × cores.”

| Field (typical) | Meaning |
|-----------------|--------|
| `wall_s` | Total run elapsed seconds |
| `batch_wall_s` | One baseline batch elapsed seconds |
| `t_compute_ms` | Time waiting on worker `RUN_BATCH` (per replica) |
| `t_coord_ms` | Coordinator-side round time including barrier + swap I/O |

Use wall time for **cost**. Compare science under a **fixed proposal budget**
(or a declared equal wall budget) so faster machines do not fake “better MCMC.”

### Proposal budget

Number of Metropolis–Hastings **proposals attempted** (Niya `run(n)` attempts
`n-1` proposals). Fair PT vs baseline comparisons should match total proposals
(or clearly state wall-clock equality instead).

### Proposals per second (`propos/s`)

`proposals / wall_time`. Throughput only — not mixing quality.

### Energy / loss \(E\)

Untempered scalar energy (Niya total loss for the MVP contract). Lower is
often “better” for this loss, but the scientific interest is the **trajectory**
and cold-chain exploration, not a single final number from a toy run.

Reported in STATUS / metrics as `energy` or `E`. Temperature scales the
**accept rule**, not the definition of reported \(E\).

### Local acceptance rate \(a_{\mathrm{local}}\)

Fraction of local proposals accepted in a batch (and optionally cumulative
over the run).

- **Diagnostic** for proposal aggressiveness and tempering.
- Hot chains often show higher \(a_{\mathrm{local}}\) by construction.
- Cold \(a_{\mathrm{local}}\) need **not** rise for PT to help mixing.

### Swap acceptance rate \(a_{\mathrm{swap}}\) (PT only)

`swap_accepts / swap_attempts` for coordinator temperature-exchange proposals.

- Ladder **hygiene** (rule-of-thumb band often cited ~20–40%; not a law).
- \(a_{\mathrm{swap}} \approx 1\) on a tiny synthetic usually means energies were
  nearly identical — not proof of scientific gain.

### Temperature \(T\) / cold worker

Each replica’s current temperature. After temperature-exchange swaps, the
**cold** label (\(T=1\)) may move between worker ids. Always report metrics
for the **cold label**, not a fixed worker id, when claiming PT benefits.

### Fingerprint

Hash / record of config, seeds, and software identity so a run can be cited
and repeated. Stored with baseline outputs (`fingerprint.json`).

---

## Metric roles by experiment type

| Experiment | Must log | Success looks like |
|------------|----------|-------------------|
| Integration / smoke | Job PASS, optional timings | TCP + process placement works |
| Single-chain Bakari/Stancomb baseline | wall, proposals, \(a_{\mathrm{local}}\), \(E\) trajectory, fingerprint | Reproducible cold reference |
| Dual-cold, exchange off | Same + two workers | Equal-resource non-PT control |
| PT | Above + \(a_{\mathrm{swap}}\), \(T\) map, cold \(E\) | Cold exploration better than equal-resource control at same budget |

---

## Poster / paper discipline

- Put **equal-budget cold vs PT** (and Bakari-path baseline) on the poster.
- Keep early toy synthetic runs labeled **integration only** (e.g. \(a_{\mathrm{local}}=1\) everywhere).
- Do not headline “higher acceptance” as the PT result unless you mean a
  carefully defined cold-chain mixing metric.
