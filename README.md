# Distributed MCMC State-Exchange Runtime

This repository pairs the GPL-3.0 `geostatisticalMCMC` scientific implementation
with project-specific adapters, replica workers, and a future C++ distributed
parallel-tempering runtime.

The imported scientific code is isolated in
`MCMC_implementation/geostatisticalMCMC/`; new runtime integration work belongs
in the sibling project directories and `cpp_runtime/`.

See `docs/README.md` for the architecture scaffold.
