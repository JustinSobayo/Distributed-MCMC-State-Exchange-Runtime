# Python two-replica PT coordinator

This is the first vertical slice of parallel tempering: a **Python** TCP
coordinator plus two outbound replica workers. The C++ coordinator comes later
and should speak the same protocol.

## What it does

Each round:

1. Both workers `RUN_BATCH`
2. Barrier on finite STATUS energies / local accept counters
3. If `exchange.enabled`, coordinator draws one \(u\sim U[0,1)\) and accepts a
   temperature swap with
   \[
   P=\min\!\big(1,\exp[(1/T_A-1/T_B)(E_A-E_B)]\big)
   \]
4. On accept: `SET_TEMPERATURE` on both workers (beds stay local)
5. Log round metrics; after all rounds, `SHUTDOWN`

Local Metropolis already uses \(T\) inside the bundled Niya copy.

## Run

From the repository root, in the scientific env:

```bash
python MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/two_replica_pt_synthetic.yaml
```

Equal-resource cold baseline (no swaps, both \(T=1\)):

```bash
python MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/two_replica_baseline_cold.yaml
```

Stancomb dual-cold and PT (short smoke budgets; raise `rounds` / `batch_n_iterations` later):

```bash
python MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/two_replica_stancomb_baseline_cold.yaml

python MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/two_replica_stancomb_pt.yaml
```

Workers are launched as **separate processes** (required: spectral RNG overlay
is process-global). Both workers receive identical science settings
(`--problem`, `--data-dir`, `--sigma-mc`); only seeds / replica id / temperature differ.
On REGISTER the coordinator checks matching science fingerprints (`problem`,
`bed_shape`, `data_dir`, `sigma_mc`).

## Outputs

Under the configured `runtime.output_dir`:

- `summary.json` — swap attempts/accepts, `a_swap`, final T map, science fingerprint
- `round_metrics.json` / `.csv` — per-round \(E\), \(T\), `a_local`, `p_swap`, timings
- `resolved_launch_config.yaml` — config with the bound coordinator port

## Tests

```bash
cd MCMC_implementation
python -m unittest tests.test_pt_exchange tests.test_pt_coordinator_loop \
  tests.test_stancomb_pt_enablement -v
```
