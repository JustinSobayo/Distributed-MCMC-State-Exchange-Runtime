# Decision: synthetic PT benchmarks on HiPerGator multi-node

**Status:** Locked for the next rigorous benchmarking campaign  
**Date:** 2026-11-05

## Decision

Run **synthetic-data** parallel tempering / baseline experiments on **HiPerGator**, using a **multi-node** allocation so coordinator and workers communicate over **real cross-node TCP** (same stack as production placement).

This is **not** “synthetic networking.” Science problem = synthetic CRF; **testing environment** = multi-node cluster fabric.

## Why this split

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Likelihood / grid | Synthetic (small, controlled) | Fast iteration, reproducible seeds, fewer data confounders |
| Placement / network | HiPerGator ≥2 nodes | Stress dial-out TCP, barriers, timeouts under real RTT—not localhost |
| Compare later | Same harness on Stancomb | Science claim on real glacier after method+platform are trusted |

Same-node HPG or laptop runs remain useful for **debug**; they are not the acceptance environment for this campaign.

## What “pass” means for this environment

1. Jobs schedule with coordinator on one node, workers on the allocation (at least one worker on a different node than the coordinator for the multi-node claim).
2. Length-prefixed JSON control plane completes rounds without spurious timeouts.
3. Equal-resource metrics are collected under that placement:
   - cold single-chain baseline (optional debug),
   - two cold workers, `exchange.enabled: false`,
   - PT with `temperatures` including one `1.0` and exchange on.
4. Outputs (`summary.json`, `round_metrics`, fingerprints) land on Blue under a known directory.

## Out of scope for this campaign

- Declaring Stancomb/real-glacier PT gains  
- Unix domain sockets (same-node optimization only)  
- C++ coordinator (Python coordinator is fine if it speaks the locked protocol)  
- Bed/state shipping  

## Implications for engineering

- Need a **SLURM multi-node launcher** for PT (not only `net_smoke_two_nodes.sh`): place coordinator + 2 workers, propagate host/port, point at synthetic YAML.  
- `run_two_replica_pt.py` localhost spawn is insufficient alone for the multi-node claim; use `srun`/`sbatch` process placement like the smoke tests.  
- Keep synthetic grid modest so wall-clock is dominated by a measurable number of batches/rounds, not days of science burn.

## One-line summary

**Synthetic problem, multi-node HiPerGator TCP** — validate PT + coordination under cluster networking before promoting the same harness to real glacier data.
