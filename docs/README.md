# Documentation

The scientific implementation is maintained separately under
`MCMC_implementation/geostatisticalMCMC/` and is treated as an unchanged
external workload. The runtime integrates through a minimal adapter interface
rather than requiring a rewrite of Niya's MCMC loop.

Project integration is organized as:

- `MCMC_implementation/adapters/` — Python wrapper (`run_batch`, energy, temperature, checkpoint)
- `MCMC_implementation/workers/` — per-replica entry point
- `cpp_runtime/` — C++/TCP PT coordinator (MVP: temperature exchange)
- `slurm/` — HiPerGator / SLURM + Apptainer orchestration

Project notes and plans live in this folder:

- `benchmark_metrics.md` — glossary of wall time, \(E\), \(a_{\mathrm{local}}\), \(a_{\mathrm{swap}}\), fingerprint (what we track and why)
- `../benchmarks/README.md` — dated run archive layout; points at the metrics glossary
- `single_chain_baseline.md` — runnable synthetic CPU cold baseline, metrics, fingerprints, and output protocol
- `python_pt_coordinator.md` — Python two-replica PT loop (swap math, launcher, metrics)
- `parallel_tempering_implementation_plan.md` — locked PT engineering decisions and build order
- `notes.md` — working notes / Stancomb orientation
- `specification.md` — full implementation plan
- `pt_temperature_energy_investigation.md` — PT temperature vs accept rule
- `replica_worker_implementation_plan.md` — asyncio Python worker (**workers connect outbound**) + agent handoff context
- `hipergator_outbound_connect_smoke_test.md` — short SLURM TCP proof (coordinator listens, worker dials) before full worker work
- `hipergator_class_access.md` — SSH, compute/dev sessions, Blue paths, and how to `cd` to your class folder
