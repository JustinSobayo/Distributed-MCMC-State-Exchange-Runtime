# Documentation

The scientific implementation is maintained separately under
`MCMC_implementation/geostatisticalMCMC/`. Project integration is organized as:

- `MCMC_implementation/adapters/` — scientific-model boundary
- `MCMC_implementation/workers/` — per-replica entry point
- `cpp_runtime/` — distributed state-exchange runtime
- `slurm/` — scheduler orchestration
