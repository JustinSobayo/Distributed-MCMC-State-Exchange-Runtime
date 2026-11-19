# Distributed MCMC State-Exchange Runtime

A distributed runtime for parallel tempering MCMC on glacier bed / topography problems (Stancomb Wills via `gstatsMCMC`). Experiments are configured with **YAML** and launched from the command line (no GUI).

**Author:** Justin Sobayo

---

## Poster

<img width="1055" height="802" alt="image" src="https://github.com/user-attachments/assets/69490442-5910-4116-97d4-ff957feac9d1" />


---

## Setup

```bash
conda env create -f MCMC_implementation/environment.yml
conda activate gstatsMCMC
```

On HiPerGator, activate your existing env instead (example):

```bash
conda activate /blue/gly4930/<user>/mcmc_runtime/envs/gstatsMCMC
```

Run long jobs on a **compute** node (`srun`), not a login node.

---

## How to use

1. Pick or edit a YAML config in `MCMC_implementation/configs/`.
2. From the **repo root**, launch with the CLI:

```bash
python MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/four_replica_stancomb_pt.yaml
```

Matched cold baseline (exchange off):

```bash
python MCMC_implementation/scripts/run_two_replica_pt.py \
  --config MCMC_implementation/configs/four_replica_stancomb_baseline_cold.yaml
```

Or run the sequential campaign script:

```bash
bash MCMC_implementation/scripts/run_stancomb_long_campaign.sh
```

### YAML knobs (experiment interface)

| Field | What it controls |
|-------|------------------|
| `sampling.replicas` | Number of worker processes |
| `sampling.temperatures` | Temperature ladder |
| `sampling.rounds` | Number of coordinator rounds |
| `sampling.batch_n_iterations` | Proposals per round per worker |
| `exchange.enabled` | Turn temperature exchange on/off |
| `exchange.pairing` | e.g. `neighbor_odd_even` |
| `runtime.output_dir` | Where run outputs are written |

Example:

```yaml
sampling:
  replicas: 4
  temperatures: [1.0, 1.01, 1.025, 1.05]
  batch_n_iterations: 101
  rounds: 2000
exchange:
  enabled: true
  pairing: neighbor_odd_even
runtime:
  output_dir: results/my_run
```

Outputs are written under `results/` (gitignored).
