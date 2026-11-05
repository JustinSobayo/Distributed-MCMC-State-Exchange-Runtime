# Single-chain cold baseline

This harness establishes a reproducible single-chain, T=1 cold baseline for
later parallel-tempering comparisons. It records running local acceptance,
refreshed untempered energy, wall time, proposals/sec, and a software/config
fingerprint. The shipped problem is **synthetic**, not Stancomb-Wills.

From the repository root, in the scientific Python environment:

```bash
python -m pip install -r MCMC_implementation/requirements-baseline.txt
python MCMC_implementation/scripts/run_single_chain_baseline.py \
  --config MCMC_implementation/configs/single_chain_cold_baseline.yaml
```

The profile runs 40 batches of 51 iterations, totaling **2,000 proposals**.
Niya's `run(n)` includes the starting state at index zero, so each batch
attempts `n - 1` proposals; acceptance counts only `steps[1:]`. The harness
checks that the returned cache has exactly `n` binary entries, beginning with
false. It resumes the same bed and both live RNG streams across batches through
`TopographyMCMCAdapter`, which uses `only_save_last_bed=True`. The existing
spectral RNG overlay directs spectral noise through the RF generator.

`experiment.seed` defaults the chain seed (`rng_seed`) and RF seed (`seed + 1`).
Both can be overridden explicitly. No global NumPy seed is set. Sampling
temperature must equal 1.0 and exchange is always disabled. The current local
scientific acceptance rule is `exp((E_prev - E_next) / T)` with `T=1.0`, which
matches the original untempered Metropolis behavior. This harness keeps
temperature fixed at 1.0 and exchange disabled.

Outputs are written to `results/single_chain_cold_baseline/`:

- `summary.json`: final accepted/attempted counts, `a_local`, `energy_final`,
  `wall_s`, `proposals_per_second`, proposal budget, and full fingerprint.
- `batch_metrics.csv`: deltas, running totals, energy, batch timing, cumulative
  wall time and throughput, one row per batch.
- `fingerprint.json`: resolved config, YAML path/hash, seeds, grid/dtype,
  temperature/exchange, git revision/status, source paths/hashes, package
  versions, Python executable/version, host, and platform.

Wall time uses `perf_counter()` from the first batch start through the final
batch end. It includes metrics, CSV writing, and terminal logging between
batches, but excludes setup, fingerprint construction, and final serialization.
The final row and summary use the same ending timestamp. No warm-up proposals
are excluded. `budget_mode: proposals` describes the implemented stopping rule;
fixed wall-clock stopping is future work.

Paths passed to `--config` are relative to the calling directory. Relative output
paths are anchored to the repository. Use `--output-dir results/another_run` to
preserve separate runs; rerunning in the same directory replaces its artifacts.
Results are gitignored, so copy them separately for presentations.

For a short smoke run, copy the YAML and set `num_batches: 2` and
`batch_n_iterations: 3` (four attempted proposals). Tests can run with:

```bash
python -m unittest discover -s MCMC_implementation/tests \
  -p test_single_chain_baseline.py -v
# Full existing suite, if pytest is installed:
python -m pytest MCMC_implementation/tests
```

`backend: cuda` and `problem: stancomb` are reserved but fail explicitly until
their builders/adapters are wired. The current adapter uses the repository-local
CPU scientific package. Use the same backend, grid, problem, and timing budget
for later PT comparisons; synthetic CPU results do not establish GPU or
Stancomb PT gains. Coordinator and swaps are outside this deliverable.
